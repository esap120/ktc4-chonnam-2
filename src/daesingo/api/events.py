"""Bounded API telemetry; an unavailable sink cannot hold an HTTP response."""
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread

from daesingo.common.logging import copy_context_call, log_event_best_effort


class ApiEvents:
    """One daemon consumer, at most 128 queued events, drop on saturation.

    Correlation is captured at submission, not borrowed from another request.
    No fallback raw logging: blocked/broken sinks are operationally lossy.
    Shutdown waits at most one second; cannot cancel arbitrary logger code.
    Fatal sink exceptions are returned to the owner by close, never printed by
    threading.excepthook. Ordinary exceptions remain best-effort diagnostics.
    A confirmed startup failure may close without draining its diagnostic;
    healthy queued work can still finish, but process exit takes precedence.
    """
    def __init__(self, logger):
        self.logger = logger
        self.queue = Queue(maxsize=128)
        self.closed = Event()
        self.lock = Lock()
        self.thread = None
        self.failure = None

    def emit(self, event: str, **fields):
        callback = copy_context_call(log_event_best_effort, self.logger, event, **fields)
        with self.lock:
            if self.closed.is_set():
                return
            try:
                self.queue.put_nowait(callback)
            except Full:
                return
            if self.thread is None:
                thread = Thread(target=self._run, daemon=True, name="api-events")
                try:
                    thread.start()
                except BaseException as error:
                    # Thread.start can be interrupted after native launch. An
                    # already running consumer owns its item and needs joining.
                    started = getattr(thread, "ident", None) is not None
                    if started:
                        self.thread = thread
                    if started or not isinstance(error, Exception):
                        self.closed.set()
                    try:
                        self.queue.get_nowait()
                    except Empty:
                        pass
                    else:
                        self.queue.task_done()
                    if not isinstance(error, Exception):
                        raise
                    return
                self.thread = thread

    def _run(self):
        while not self.closed.is_set() or not self.queue.empty():
            try:
                callback = self.queue.get(timeout=.05)
            except Empty:
                continue
            try:
                callback()
            except Exception:
                pass
            except BaseException as error:
                with self.lock:
                    self.failure = error
                    self.closed.set()
                    while True:
                        try:
                            self.queue.get_nowait()
                        except Empty:
                            break
                        self.queue.task_done()
                return
            finally:
                self.queue.task_done()

    def close(self, *, drain=True):
        with self.lock:
            self.closed.set()
            thread = self.thread
        if drain and thread is not None:
            thread.join(timeout=1)
        with self.lock:
            failure, self.failure = self.failure, None
        if failure is not None:
            raise failure
