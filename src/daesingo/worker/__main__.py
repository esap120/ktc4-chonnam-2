"""Run a single Worker: python -m daesingo.worker."""

import logging
import signal
from threading import Event

from daesingo.common.db import create_worker_engine
from daesingo.common.logging import log_event_best_effort
from daesingo.worker.bootstrap import bootstrap
from daesingo.worker.composition import compose_worker
from daesingo.worker.registry import KindRegistry


def _failure(logger, event):
    # The process boundary must remain safe even if the sink raises a fatal.
    # Never serialize the original exception or ask stdlib to print a traceback.
    try:
        log_event_best_effort(logger, event, level=logging.ERROR)
    except BaseException:
        pass


def main() -> int:
    startup = bootstrap(revision="unknown")
    stop = Event()
    engine = None
    previous = {}
    code = 0

    def request_stop(signum, frame):
        # Handler and T1 continue; only the next idle point sees this event.
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.getsignal(sig)
            signal.signal(sig, request_stop)
        engine = create_worker_engine(startup.config.db)
        # Real Recording/Search capabilities are registered in RT-10.
        registry = KindRegistry({})
        compose_worker(engine=engine, startup=startup, registry=registry, stop=stop).run()
    except BaseException:
        stop.set()
        _failure(startup.logger, "runtime.worker.failed")
        code = 1
    finally:
        try:
            if engine is not None:
                engine.dispose()
        except BaseException:
            _failure(startup.logger, "runtime.worker.cleanup_failed")
            code = 1
        finally:
            for sig, handler in previous.items():
                try:
                    signal.signal(sig, handler)
                except BaseException:
                    _failure(startup.logger, "runtime.worker.cleanup_failed")
                    code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
