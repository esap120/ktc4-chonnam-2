"""API-owned resources; Case/command/read-port wiring belongs to RT-08(b/c)."""
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy.engine import Engine
from daesingo.common.bootstrap import Startup
from daesingo.common.db import create_api_engine, create_ready_engine
from .health import Readiness
from .storage import storage_available


@dataclass(frozen=True)
class ApiComposition:
    startup: Startup
    engine: Engine
    ready_engine: Engine
    readiness: Readiness
    _lock: object = field(default_factory=Lock, repr=False, compare=False)
    _closed: bool = field(default=False, init=False, repr=False, compare=False)
    cleanup_failed: bool = field(default=False, init=False, repr=False, compare=False)

    def close(self):
        with self._lock:
            if self._closed:
                return
            object.__setattr__(self, "_closed", True)
        failure = None
        for close in (self.readiness.close, self.ready_engine.dispose, self.engine.dispose):
            try:
                close()
            except BaseException as error:
                object.__setattr__(self, "cleanup_failed", True)
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure


def compose_api(startup: Startup) -> ApiComposition:
    config = startup.config
    if config.service != "api" or config.ready is None:
        raise ValueError("API startup configuration required")
    engine = create_api_engine(config.db)
    ready_engine = None
    try:
        ready_engine = create_ready_engine(config.db, config.ready)
        def db_probe():
            with ready_engine.connect() as connection:
                return connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        readiness = Readiness(settings=config.ready, db_probe=db_probe,
                              storage_probe=lambda: storage_available(config.media_root), logger=startup.logger)
        return ApiComposition(startup, engine, ready_engine, readiness)
    except BaseException:
        # Construction can fail before a composition/lifespan owner exists.
        # Try every allocated engine, retaining the original fatal/error policy.
        for allocated in (ready_engine, engine):
            if allocated is not None:
                try:
                    allocated.dispose()
                except BaseException:
                    pass
        raise
