"""Supported API process boundary: python -m daesingo.api --revision <revision>."""
import argparse
import logging
import signal
from contextlib import contextmanager
import uvicorn
from .app import create_app


class _QuietParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's message can contain untrusted argv and source paths.
        raise SystemExit(1) from None


def _port(value):
    port = int(value)
    if not 0 <= port <= 65535:
        raise ValueError("invalid port")
    return port


@contextmanager
def _server_logging():
    # Disable only the server's named loggers for this invocation. Keep foreign
    # handlers alive and restore any Uvicorn config edits on every exit path.
    saved = []
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        saved.append((logger, logger.handlers, logger.disabled, logger.propagate))
        logger.disabled = True
    try:
        yield
    finally:
        for logger, handlers, disabled, propagate in saved:
            logger.handlers, logger.disabled, logger.propagate = handlers, disabled, propagate


def _failure(composition, event):
    if composition is not None:
        try:
            composition.readiness.events.emit(event, status="FAILED")
        except BaseException:
            pass


def main(argv=None):
    parser = _QuietParser(description="Daesingo API (one process)")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=_port, default=8000)
    args = parser.parse_args(argv)
    signals = (signal.SIGINT, signal.SIGTERM)
    if hasattr(signal, "SIGBREAK"):
        signals += (signal.SIGBREAK,)
    previous = {sig: signal.getsignal(sig) for sig in signals}
    composition, code = None, 0
    serving = False
    try:
        app = create_app(revision=args.revision)
        composition = getattr(getattr(app, "state", None), "composition", None)
        # Concrete app + workers=1 defeat WEB_CONCURRENCY; safe events own logs.
        with _server_logging():
            serving = True
            uvicorn.run(app, host=args.host, port=args.port, workers=1, reload=False,
                        access_log=False, log_config=None)
    except KeyboardInterrupt:
        # Only an interrupt during the server invocation is graceful. Bootstrap
        # and composition have not established a running API and must fail.
        if not serving:
            code = 1
    except BaseException:
        # Like Worker, intentional SystemExit cannot select success/arbitrary
        # exit codes or disclose string payloads. Library exceptions stay local.
        code = 1
        _failure(composition, "api.server.failed")
    finally:
        try:
            if composition is not None:
                composition.close()
                # Uvicorn catches lifespan exceptions internally. Once-only
                # disposal must still retain failure for the process boundary.
                if getattr(composition, "cleanup_failed", False):
                    code = 1
        except BaseException:
            code = 1
            _failure(composition, "api.cleanup.failed")
        finally:
            for sig, handler in previous.items():
                try:
                    if signal.getsignal(sig) != handler:
                        signal.signal(sig, handler)
                except BaseException:
                    code = 1
                    _failure(composition, "api.cleanup.failed")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
