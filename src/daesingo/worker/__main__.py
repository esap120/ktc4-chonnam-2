"""Run a single Worker: python -m daesingo.worker."""

import logging
import signal
from threading import Event

from daesingo.common.db import create_worker_engine
from daesingo.common.logging import log_event_best_effort
from daesingo.worker.bootstrap import bootstrap
from daesingo.worker.composition import compose_worker
from daesingo.worker.registry import KindRegistry


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
    except Exception:
        log_event_best_effort(startup.logger, "runtime.worker.failed", level=logging.ERROR)
        code = 1
    finally:
        try:
            if engine is not None:
                engine.dispose()
        except Exception:
            log_event_best_effort(startup.logger, "runtime.worker.cleanup_failed", level=logging.ERROR)
            code = 1
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
