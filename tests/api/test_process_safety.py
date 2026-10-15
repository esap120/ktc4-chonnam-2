"""Real subprocess safety: no release signal may be needed to exit."""
import subprocess
import sys
import textwrap

import pytest


def run_child(source, *, timeout=5):
    child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", textwrap.dedent(source)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = child.communicate(timeout=timeout)
        return child.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        child.kill()
        stdout, stderr = child.communicate(timeout=5)
        pytest.fail(f"owned child exceeded {timeout}s (stdout={stdout!r}, stderr={stderr!r})")
    finally:
        assert child.poll() is not None


def test_stalled_handler_write_does_not_deadlock_interpreter_shutdown():
    code, stdout, stderr = run_child('''
        import io, json, logging
        from threading import Event
        from daesingo.api.events import ApiEvents
        from daesingo.common.logging import configure_logging
        entered = Event()
        class StalledStream(io.StringIO):
            def write(self, value):
                entered.set()
                Event().wait()  # Never released; actual handler stream.write.
        class ForeignHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.closed_by_api = False
            def emit(self, record): pass
            def close(self):
                self.closed_by_api = True
                super().close()
        foreign = logging.getLogger("third.party")
        handler = ForeignHandler()
        foreign.addHandler(handler)
        root_handlers = tuple(logging.getLogger().handlers)
        events = ApiEvents(configure_logging("api", stream=StalledStream()))
        events.emit("api.request.completed", status="200")
        assert entered.wait(2)
        events.close()
        assert tuple(logging.getLogger().handlers) == root_handlers
        assert foreign.handlers == [handler] and not handler.closed_by_api
        print(json.dumps({"write_entered": True, "close_returned": True}), flush=True)
        # Real interpreter atexit must finish without releasing the writer.
    ''')
    assert code == 0 and stderr == b""
    assert b'"close_returned": true' in stdout


def test_unread_stdout_pipe_does_not_hold_interpreter_buffer_lock():
    source = '''
        from threading import Event
        from daesingo.api.events import ApiEvents
        from daesingo.common.logging import configure_logging
        entered = Event()
        logger = configure_logging("api")
        original = logger.handlers[0].stream
        class ObservedOutput:
            def write(self, value):
                entered.set()
                original.write(value)
            def flush(self): original.flush()
        logger.handlers[0].stream = ObservedOutput()
        events = ApiEvents(logger)
        events.emit("api.request.completed", keys=["KEY"] * 100000)
        assert entered.wait(2)
        events.close()
    '''
    child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", textwrap.dedent(source)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # Deliberately never drain the pipe while the writer/interpreter lives.
        assert child.wait(timeout=5) == 0
        stdout, stderr = child.communicate(timeout=5)
        # Windows may block the entire large os.write before any bytes arrive.
        assert len(stdout) < 600000 and stderr == b""
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_failed_sink_with_unread_stderr_does_not_deadlock_interpreter():
    source = '''
        import io, time
        from daesingo.api.events import ApiEvents
        from daesingo.common.logging import configure_logging
        class BrokenStream(io.StringIO):
            def write(self, value): raise OSError("PRIVATE_WRITE_FAILURE")
        events = ApiEvents(configure_logging("api", stream=BrokenStream()))
        for _ in range(5000):
            events.emit("api.request.completed", status="200")
            time.sleep(.0002)
        events.close()
        print("close_returned", flush=True)
    '''
    child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", textwrap.dedent(source)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # No stderr drain/release while alive, including real interpreter exit.
        assert child.wait(timeout=9) == 0
        stdout, stderr = child.communicate(timeout=5)
        assert stdout.strip() == b"close_returned"
        assert b"log.write.failed" in stderr and b"PRIVATE" not in stderr
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


@pytest.mark.parametrize("fatal", ["KeyboardInterrupt", "SystemExit", "BaseException"])
def test_event_fatal_reaches_owner_without_thread_traceback(api_startup, fatal):
    from daesingo.api.events import ApiEvents
    startup, stream = api_startup
    failure = getattr(__import__("builtins"), fatal)("PRIVATE_LOG_FAILURE")
    def fail(record):
        raise failure
    startup.logger.addFilter(fail)
    events = ApiEvents(startup.logger)
    try:
        events.emit("api.request.completed", status="200")
        with pytest.raises(type(failure)) as caught:
            events.close()
        assert caught.value is failure
        assert not events.thread.is_alive()
        assert events.queue.unfinished_tasks == 0
        assert "PRIVATE" not in stream.getvalue()
    finally:
        startup.logger.removeFilter(fail)


def test_normal_event_drain_flushes_sink_and_releases_owned_thread(api_startup):
    from daesingo.api.events import ApiEvents
    from daesingo.common.logging import bind_context
    startup, stream = api_startup
    events = ApiEvents(startup.logger)
    with bind_context(trace_id="tr_request", case_id="case", job_id="job", execution_id="exec"):
        for _ in range(4):
            events.emit("api.request.completed", status="200")
    events.close()
    import json
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(rows) == 4
    assert all((r["trace_id"], r["case_id"], r["job_id"], r["execution_id"]) ==
               ("tr_request", "case", "job", "exec") for r in rows)
    assert not events.thread.is_alive() and events.queue.unfinished_tasks == 0


@pytest.mark.parametrize("fatal", [KeyboardInterrupt, SystemExit, BaseException])
def test_thread_start_fatal_propagates_and_cleans_queue(api_startup, monkeypatch, fatal):
    from daesingo.api.events import ApiEvents
    startup, stream = api_startup
    class FailedThread:
        def __init__(self, **kwargs): pass
        def start(self): raise fatal("PRIVATE_START_FAILURE")
    monkeypatch.setattr("daesingo.api.events.Thread", FailedThread)
    events = ApiEvents(startup.logger)
    with pytest.raises(fatal):
        events.emit("api.request.completed", status="200")
    events.close()
    assert events.thread is None and events.queue.unfinished_tasks == 0


COMPOSITION_FAILURE_WITH_STALLED_WRITE = '''
import io
from pathlib import Path
from threading import Event
from types import MappingProxyType
import daesingo.api.app as module
from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig
from daesingo.common.logging import configure_logging
entered = Event()
class StalledStream(io.StringIO):
    def write(self, value):
        print("write_entered", flush=True)
        entered.set()
        Event().wait()  # No release, in the actual handler write.
original_emit = module.ApiEvents.emit
def emit(self, *args, **kwargs):
    original_emit(self, *args, **kwargs)
    assert entered.wait(2)  # Prove actual sink entry before failure exit.
module.ApiEvents.emit = emit
config = RuntimeConfig.from_mapping("api", {
    "DAESINGO_RUNTIME_DB_URL": "mysql+pymysql://user:PRIVATE_SECRET@127.0.0.1:1/test",
    "DAESINGO_RUNTIME_MEDIA_ROOT": str(Path.cwd() / "PRIVATE_PATH"),
    "DAESINGO_RUNTIME_API_TEMP_ROOT": str(Path.cwd() / "PRIVATE_PATH"),
})
startup = Startup(config, MappingProxyType({}), configure_logging("api", stream=StalledStream()))
def fail(startup):
    raise RuntimeError("PRIVATE_EXCEPTION mysql+pymysql://user:PRIVATE_SECRET /PRIVATE_PATH")
module.compose_api = fail
module.create_app(startup=startup)
'''


def test_composition_failure_outranks_stalled_handler_write():
    # Keep the original total-process check: imports still consume its 5s budget.
    code, stdout, stderr = run_child(COMPOSITION_FAILURE_WITH_STALLED_WRITE)
    assert code == 1 and stdout.strip() == b"write_entered" and stderr == b""
    assert b"PRIVATE" not in stdout + stderr


def test_composition_failure_exits_within_five_seconds_after_ready_trigger(tmp_path):
    import json
    from process_probe import instrument_stalled_composition, run_triggered_child
    source = instrument_stalled_composition(COMPOSITION_FAILURE_WITH_STALLED_WRITE, tmp_path)
    code, stdout, stderr = run_triggered_child(source, tmp_path)
    assert code == 1 and stderr == b""
    assert b"PRIVATE" not in stdout + stderr
    phases = [json.loads(line)["phase"] for line in stdout.splitlines()]
    assert phases == ["interpreter_entered", "imports_done", "logger_config_ready", "ready",
                      "before_composition_failure", "write_entered", "system_exit_returned",
                      "before_atexit", "atexit"]


@pytest.mark.parametrize("fatal", ["KeyboardInterrupt", "SystemExit", "BaseException"])
def test_composition_failure_outranks_fatal_diagnostic(api_startup, monkeypatch, fatal, capsys):
    import daesingo.api.app as module
    startup, stream = api_startup
    def fail(startup): raise RuntimeError("PRIVATE_COMPOSITION")
    def fail_log(record): raise getattr(__import__("builtins"), fatal)("PRIVATE_LOG")
    monkeypatch.setattr(module, "compose_api", fail)
    startup.logger.addFilter(fail_log)
    try:
        with pytest.raises(BaseException) as caught:
            module.create_app(startup=startup)
        assert isinstance(caught.value, SystemExit)
        assert caught.value.code == 1
        assert capsys.readouterr().err == ""
        assert stream.getvalue() == ""
    finally:
        startup.logger.removeFilter(fail_log)


@pytest.mark.parametrize("arguments", [
    ["--port", "-1"],
    ["--revision", "test", "--port", "-1"],
    ["--revision", "test", "--port", "65536"],
    ["--revision", "test", "--port", "PRIVATE_INVALID_PORT"],
])
def test_invalid_port_is_quiet_before_bootstrap_or_db(arguments):
    result = subprocess.run([sys.executable, "-B", "-m", "daesingo.api", *arguments],
                            capture_output=True, timeout=5)
    assert result.returncode == 1 and result.stdout == b"" and result.stderr == b""
    code, stdout, stderr = run_child(f'''
        import daesingo.api.__main__ as module
        def forbidden(**kwargs):
            print("PRIVATE_BOOTSTRAP_CALLED", flush=True)
            raise AssertionError("DB/composition must not run")
        module.create_app = forbidden
        raise SystemExit(module.main({arguments!r}))
    ''')
    assert code == 1 and stdout == b"" and stderr == b""


@pytest.mark.parametrize("phase,expected", [("bootstrap", 1), ("composition", 1), ("server", 0)])
def test_keyboard_interrupt_distinguishes_startup_from_serving(phase, expected):
    code, stdout, stderr = run_child(f'''
        import io, logging, signal
        from pathlib import Path
        from types import MappingProxyType
        from sqlalchemy import event
        import daesingo.api.__main__ as cli
        import daesingo.api.app as application
        import daesingo.api.composition as wiring
        from daesingo.common.bootstrap import Startup
        from daesingo.common.config import RuntimeConfig
        from daesingo.common.logging import configure_logging
        phase = {phase!r}
        signals = (signal.SIGINT, signal.SIGTERM)
        before = {{sig: signal.getsignal(sig) for sig in signals}}
        class ForeignHandler(logging.NullHandler):
            closed_by_api = False
            def close(self):
                self.closed_by_api = True
                super().close()
        handler = ForeignHandler()
        foreign = logging.getLogger("uvicorn.error")
        foreign.addHandler(handler)
        saved = (tuple(foreign.handlers), foreign.disabled, foreign.propagate)
        stream = io.StringIO()
        config = RuntimeConfig.from_mapping("api", {{
            "DAESINGO_RUNTIME_DB_URL": "mysql+pymysql://user:PRIVATE_SECRET@127.0.0.1:1/test",
            "DAESINGO_RUNTIME_MEDIA_ROOT": str(Path.cwd()),
            "DAESINGO_RUNTIME_API_TEMP_ROOT": str(Path.cwd()),
        }})
        startup = Startup(config, MappingProxyType({{}}), configure_logging("api", stream=stream))
        disposed = []
        original_api, original_ready = wiring.create_api_engine, wiring.create_ready_engine
        def interrupt():
            for sig in signals:
                signal.signal(sig, lambda *args: None)
            raise KeyboardInterrupt("PRIVATE_INTERRUPT /PRIVATE_PATH mysql://PRIVATE_SECRET")
        def bootstrap(**kwargs):
            assert kwargs == {{"revision": "test"}}
            if phase == "bootstrap": interrupt()
            return startup
        def api_engine(*args):
            engine = original_api(*args)
            event.listen(engine, "engine_disposed", lambda engine: disposed.append("api"))
            return engine
        def ready_engine(*args):
            if phase == "composition": interrupt()
            engine = original_ready(*args)
            event.listen(engine, "engine_disposed", lambda engine: disposed.append("ready"))
            return engine
        def serve(app, **kwargs):
            assert phase == "server"
            assert kwargs == {{"host": "127.0.0.1", "port": 8123, "workers": 1,
                              "reload": False, "access_log": False, "log_config": None}}
            interrupt()
        application.bootstrap = bootstrap
        wiring.create_api_engine, wiring.create_ready_engine = api_engine, ready_engine
        cli.uvicorn.run = serve
        result = cli.main(["--revision", "test", "--port", "8123"])
        assert all(signal.getsignal(sig) == before[sig] for sig in signals)
        assert (tuple(foreign.handlers), foreign.disabled, foreign.propagate) == saved
        assert not handler.closed_by_api
        assert disposed == ({{"bootstrap": [], "composition": ["api"], "server": ["ready", "api"]}}[phase])
        assert "PRIVATE" not in stream.getvalue()
        raise SystemExit(result)
    ''')
    assert code == expected and stdout == b"" and stderr == b""


@pytest.mark.parametrize("failure,expected", [
    ("RuntimeError('PRIVATE_SERVER /PRIVATE_PATH mysql://PRIVATE_SECRET')", 1),
    ("OverflowError('PRIVATE_OVERFLOW')", 1),
    ("KeyboardInterrupt('PRIVATE_INTERRUPT')", 0),
    ("SystemExit(0)", 1),
    ("SystemExit(7)", 1),
    ("SystemExit('PRIVATE_EXIT')", 1),
    ("BaseException('PRIVATE_FATAL')", 1),
])
def test_server_failure_cleanup_signal_and_foreign_logger_restoration(failure, expected):
    code, stdout, stderr = run_child(f'''
        import json, logging, signal
        from types import SimpleNamespace
        import daesingo.api.__main__ as module
        signals = (signal.SIGINT, signal.SIGTERM)
        previous = {{sig: signal.getsignal(sig) for sig in signals}}
        logger = logging.getLogger("uvicorn.error")
        foreign = logging.NullHandler()
        logger.addHandler(foreign)
        original = (tuple(logger.handlers), logger.disabled, logger.propagate)
        closed = []
        app = SimpleNamespace(state=SimpleNamespace(composition=SimpleNamespace(close=lambda: closed.append(1))))
        module.create_app = lambda **kwargs: app
        def run(app, **kwargs):
            assert kwargs["workers"] == 1 and kwargs["port"] == 8123
            assert kwargs["host"] == "127.0.0.1"
            for sig in signals:
                signal.signal(sig, lambda *args: None)
            raise {failure}
        module.uvicorn.run = run
        result = module.main(["--revision", "test", "--host", "127.0.0.1", "--port", "8123"])
        assert closed == [1]
        assert all(signal.getsignal(sig) == value for sig, value in previous.items())
        assert (tuple(logger.handlers), logger.disabled, logger.propagate) == original
        print(json.dumps({{"code": result, "cleanup": True, "signals": True}}))
        raise SystemExit(result)
    ''')
    assert code == expected and stderr == b""
    assert b'"cleanup": true' in stdout and b"PRIVATE" not in stdout + stderr


def test_composition_cleanup_is_once_and_closes_all_resources_after_fatal(api_startup):
    from daesingo.api.composition import ApiComposition
    from types import SimpleNamespace
    startup, stream = api_startup
    closed = []
    def close_ready():
        closed.append("readiness")
        raise KeyboardInterrupt("PRIVATE_CLEANUP")
    composition = ApiComposition(startup,
        SimpleNamespace(dispose=lambda: closed.append("pool")),
        SimpleNamespace(dispose=lambda: closed.append("ready_engine")),
        SimpleNamespace(close=close_ready))
    with pytest.raises(KeyboardInterrupt):
        composition.close()
    repeated = None
    try:
        composition.close()
    except BaseException as error:
        repeated = error
    assert repeated is None
    assert closed == ["readiness", "ready_engine", "pool"]


@pytest.mark.parametrize("lifespan", [False, True])
def test_cli_real_composition_cleanup_with_and_without_lifespan(api_startup, monkeypatch, lifespan):
    from fastapi.testclient import TestClient
    import daesingo.api.__main__ as module
    from daesingo.api.app import create_app
    startup, stream = api_startup
    app = create_app(startup=startup)
    composition = app.state.composition
    disposed = []
    for label, engine in (("api", composition.engine), ("ready", composition.ready_engine)):
        original = engine.dispose
        def dispose(label=label, original=original):
            disposed.append(label)
            original()
        monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(module, "create_app", lambda **kwargs: app)
    def run(app, **kwargs):
        if lifespan:
            with TestClient(app) as client:
                assert client.get("/health/live").status_code == 200
        raise RuntimeError("PRIVATE_SERVER_FAILURE")
    monkeypatch.setattr(module.uvicorn, "run", run)
    assert module.main(["--revision", "test"]) == 1
    assert sorted(disposed) == ["api", "ready"]
    assert composition._closed and composition.readiness.events.closed.is_set()
    thread = composition.readiness.events.thread
    assert thread is None or not thread.is_alive()
    assert "PRIVATE" not in stream.getvalue()
    if not lifespan:
        assert '"event":"api.server.failed"' in stream.getvalue()


@pytest.mark.parametrize("fatal", ["RuntimeError", "KeyboardInterrupt", "SystemExit", "BaseException"])
def test_cli_cleanup_failure_is_quiet_and_restores_signals(fatal):
    code, stdout, stderr = run_child(f'''
        import signal
        from types import SimpleNamespace
        import daesingo.api.__main__ as module
        previous = signal.getsignal(signal.SIGINT)
        def close(): raise {fatal}("PRIVATE_CLEANUP")
        app = SimpleNamespace(state=SimpleNamespace(composition=SimpleNamespace(close=close)))
        module.create_app = lambda **kwargs: app
        def run(app, **kwargs): signal.signal(signal.SIGINT, lambda *args: None)
        module.uvicorn.run = run
        code = module.main(["--revision", "test"])
        assert signal.getsignal(signal.SIGINT) == previous
        raise SystemExit(code)
    ''')
    assert code == 1 and stdout == b"" and stderr == b""


@pytest.mark.parametrize("port", [0, 65535])
def test_valid_port_edges_and_normal_exit(monkeypatch, port):
    import daesingo.api.__main__ as module
    called = []
    monkeypatch.setattr(module, "create_app", lambda **kwargs: "app")
    monkeypatch.setattr(module.uvicorn, "run", lambda app, **kwargs: called.append(kwargs))
    assert module.main(["--revision", "test", "--port", str(port)]) == 0
    assert called[0]["port"] == port and called[0]["workers"] == 1


def test_uvicorn_swallowed_lifespan_cleanup_failure_still_exits_one(api_startup, monkeypatch, capsys):
    import asyncio
    from uvicorn import Config
    from uvicorn.lifespan.on import LifespanOn
    import daesingo.api.__main__ as module
    from daesingo.api.app import create_app
    startup, stream = api_startup
    app = create_app(startup=startup)
    composition = app.state.composition
    original = composition.readiness.close
    def close():
        original()
        raise RuntimeError("PRIVATE_LIFESPAN_CLEANUP")
    monkeypatch.setattr(composition.readiness, "close", close)
    monkeypatch.setattr(module, "create_app", lambda **kwargs: app)
    def run(app, **kwargs):
        async def serve():
            lifespan = LifespanOn(Config(app, log_config=None, access_log=False))
            await lifespan.startup()
            await lifespan.shutdown()
            assert lifespan.shutdown_failed  # Actual Uvicorn swallowed error.
        asyncio.run(serve())
    monkeypatch.setattr(module.uvicorn, "run", run)
    assert module.main(["--revision", "test"]) == 1
    assert composition._closed
    assert "PRIVATE" not in stream.getvalue() and capsys.readouterr().err == ""


@pytest.mark.parametrize("fatal", [RuntimeError, KeyboardInterrupt])
def test_partial_composition_closes_real_engines_if_readiness_creation_fails(api_startup, monkeypatch, fatal):
    import daesingo.api.composition as module
    startup, stream = api_startup
    engines, disposed = [], []
    for factory_name in ("create_api_engine", "create_ready_engine"):
        factory = getattr(module, factory_name)
        def create(*args, factory=factory):
            engine = factory(*args)
            engines.append(engine)
            dispose = engine.dispose
            def close():
                disposed.append(engine)
                dispose()
            monkeypatch.setattr(engine, "dispose", close)
            return engine
        monkeypatch.setattr(module, factory_name, create)
    def fail(**kwargs): raise fatal("PRIVATE_PARTIAL_COMPOSITION")
    monkeypatch.setattr(module, "Readiness", fail)
    with pytest.raises(fatal):
        module.compose_api(startup)
    assert len(engines) == 2 and set(disposed) == set(engines)


def test_actual_server_cleanup_failure_exit_and_listener_release():
    code, stdout, stderr = run_child('''
        import io, signal, socket, uvicorn
        from pathlib import Path
        from types import MappingProxyType
        import daesingo.api.__main__ as module
        from daesingo.api.app import create_app
        from daesingo.common.bootstrap import Startup
        from daesingo.common.config import RuntimeConfig
        from daesingo.common.logging import configure_logging
        config = RuntimeConfig.from_mapping("api", {
            "DAESINGO_RUNTIME_DB_URL": "mysql+pymysql://user:PRIVATE_SECRET@127.0.0.1:1/test",
            "DAESINGO_RUNTIME_MEDIA_ROOT": str(Path.cwd()),
            "DAESINGO_RUNTIME_API_TEMP_ROOT": str(Path.cwd()),
        })
        output = io.StringIO()
        startup = Startup(config, MappingProxyType({}), configure_logging("api", stream=output))
        app = create_app(startup=startup)
        composition = app.state.composition
        original = composition.readiness.close
        def close():
            original()
            raise RuntimeError("PRIVATE_LIFESPAN_CLEANUP")
        composition.readiness.close = close
        module.create_app = lambda **kwargs: app
        ports = []
        listeners = []
        async def main_loop(server):
            listener = server.servers[0].sockets[0]
            listeners.append(listener)
            ports.append(listener.getsockname()[1])
        uvicorn.Server.main_loop = main_loop
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        # Actual uvicorn.run, startup, bind(port0), shutdown and signal context.
        result = module.main(["--revision", "test", "--port", "0"])
        assert len(ports) == 1 and composition._closed
        assert listeners[0].fileno() == -1
        with socket.socket() as probe:
            probe.settimeout(.3)
            assert probe.connect_ex(("127.0.0.1", ports[0])) != 0
        assert all(signal.getsignal(sig) == handler for sig, handler in previous.items())
        assert "PRIVATE" not in output.getvalue()
        raise SystemExit(result)
    ''')
    assert code == 1 and stdout == b"" and stderr == b""


@pytest.mark.parametrize("failure", [KeyboardInterrupt("PRIVATE_START"), SystemExit("PRIVATE_START"),
                                   RuntimeError("PRIVATE_START")])
def test_thread_start_failure_after_native_launch_retains_owner(api_startup, monkeypatch, failure):
    from threading import Event, Thread
    from daesingo.api.events import ApiEvents
    startup, stream = api_startup
    entered, release = Event(), Event()
    created = []
    def slow(record):
        entered.set()
        release.wait(2)
        return True
    startup.logger.addFilter(slow)
    class InterruptedThread(Thread):
        def start(self):
            created.append(self)
            super().start()
            assert entered.wait(1)
            raise failure
    monkeypatch.setattr("daesingo.api.events.Thread", InterruptedThread)
    events = ApiEvents(startup.logger)
    try:
        caught = None
        try:
            events.emit("api.request.completed", status="200")
        except BaseException as error:
            caught = error
        assert caught is (None if isinstance(failure, Exception) else failure)
        assert events.thread is created[0]
        release.set()
        events.close()
        assert not created[0].is_alive() and events.queue.unfinished_tasks == 0
    finally:
        release.set()
        for thread in created:
            thread.join(2)
        startup.logger.removeFilter(slow)
