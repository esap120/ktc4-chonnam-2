"""Bounded readiness probes: dedicated connections, metadata only, no provider."""
from collections.abc import Callable
from threading import Event, Lock, Thread
from time import monotonic

from daesingo.common.config import ReadySettings
from daesingo.common.logging import copy_context_call
from .events import ApiEvents
from .storage import storage_available


class _Probe:
    """One outstanding probe, shared by overlapping callers within its deadline.

    Python cannot cancel blocked native filesystem/socket calls. Daemon workers
    let shutdown proceed and late DB results close their connection normally.
    A timed-out attempt is never a successful result for a later caller.
    """
    def __init__(self):
        self.lock = Lock()
        self.pending = None
        self.closed = False

    def run(self, callback: Callable[[], bool], timeout: float) -> bool:
        start = monotonic()
        if timeout <= 0:
            return False
        with self.lock:
            if self.closed:
                return False
            pending = self.pending
            if pending is None:
                pending = (Event(), [False], start + timeout)
                self.pending = pending
                launch = True
            else:
                launch = False
        done, result, deadline = pending
        if launch:
            def invoke():
                try:
                    result[0] = bool(callback()) and monotonic() <= deadline
                except Exception:
                    pass
                finally:
                    done.set()
                    with self.lock:
                        if self.pending is pending:
                            self.pending = None
            try:
                Thread(target=copy_context_call(invoke), daemon=True, name="api-ready-probe").start()
            except Exception:
                done.set()
                with self.lock:
                    self.pending = None
                return False
        completed = done.wait(max(0, min(start + timeout, deadline) - monotonic()))
        with self.lock:
            return not self.closed and completed and result[0]

    def close(self):
        with self.lock:
            self.closed = True


class Readiness:
    def __init__(self, *, settings: ReadySettings, db_probe: Callable[[], bool],
                 storage_probe: Callable[[], bool], logger):
        self.settings = settings
        self.db_probe = db_probe
        self.storage_probe = storage_probe
        self.events = ApiEvents(logger)
        self._db = _Probe()
        self._storage = _Probe()

    def check(self) -> bool:
        start = monotonic()
        deadline = start + self.settings.budget_sec
        available = True
        for name, probe, callback, timeout in (
            ("db", self._db, self.db_probe, self.settings.db_timeout_sec),
            ("storage", self._storage, self.storage_probe, self.settings.storage_timeout_sec),
        ):
            if not probe.run(callback, min(timeout, deadline - monotonic())):
                available = False
                self.events.emit("api.ready." + name + ".unavailable", status="UNAVAILABLE")
        duration = monotonic() - start
        available = available and duration <= self.settings.budget_sec
        self.events.emit("api.ready.completed", duration_ms=duration * 1000,
                             status="OK" if available else "UNAVAILABLE")
        return available

    def close(self):
        self._db.close()
        self._storage.close()
        self.events.close()
