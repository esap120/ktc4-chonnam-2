"""Entrypoint composition and signal ownership, without provider calls."""

from importlib import import_module
from io import StringIO
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
from types import SimpleNamespace
import textwrap

import pytest

from daesingo.common.jobs.execution import ExecutionContext


def test_main_composes_single_registry_and_disposes_engine_and_restores_signals(monkeypatch):
    module = import_module("daesingo.worker.__main__")
    calls, installed, restored = [], {}, []
    engine = SimpleNamespace(dispose=lambda: calls.append("dispose"))
    startup = SimpleNamespace(config=SimpleNamespace(db=object()), logger=object())
    monkeypatch.setattr(module, "bootstrap", lambda **kw: calls.append("bootstrap") or startup)
    monkeypatch.setattr(module, "create_worker_engine", lambda db: calls.append("engine") or engine)
    monkeypatch.setattr(module.signal, "getsignal", lambda sig: sig)
    def install(sig, handler):
        if callable(handler):
            installed[sig] = handler
        else:
            restored.append((sig, handler))
    monkeypatch.setattr(module.signal, "signal", install)
    def compose(**kw):
        assert kw["engine"] is engine and kw["startup"] is startup
        assert kw["registry"].dispatch(ExecutionContext("exec", "job", "case", "TEST", 1, "trace")).failure_kind == "RUNTIME_UNREGISTERED_KIND"
        def run():
            assert not kw["stop"].is_set()
            installed[signal.SIGTERM](signal.SIGTERM, None)
            assert kw["stop"].is_set()
            calls.append("loop")
        return SimpleNamespace(run=run)
    monkeypatch.setattr(module, "compose_worker", compose)
    assert module.main() == 0
    assert calls == ["bootstrap", "engine", "loop", "dispose"]
    assert set(installed) == {signal.SIGINT, signal.SIGTERM}
    assert set(restored) == {(signal.SIGINT, signal.SIGINT), (signal.SIGTERM, signal.SIGTERM)}


def test_main_disposes_resources_on_loop_error_without_raw_exception(monkeypatch):
    module = import_module("daesingo.worker.__main__")
    from daesingo.common.logging import configure_logging
    stream, calls = StringIO(), []
    startup = SimpleNamespace(config=SimpleNamespace(db=object()),
                              logger=configure_logging("worker", stream=stream))
    monkeypatch.setattr(module, "bootstrap", lambda **kw: startup)
    monkeypatch.setattr(module, "create_worker_engine", lambda db: SimpleNamespace(dispose=lambda: calls.append("dispose")))
    monkeypatch.setattr(module.signal, "getsignal", lambda sig: signal.SIG_DFL)
    monkeypatch.setattr(module.signal, "signal", lambda *args: None)
    def run():
        raise RuntimeError("/private/path secret user/provider payload")
    monkeypatch.setattr(module, "compose_worker", lambda **kw: SimpleNamespace(run=run))
    assert module.main() == 1
    assert calls == ["dispose"]
    assert json.loads(stream.getvalue())["event"] == "runtime.worker.failed"
    assert all(word not in stream.getvalue() for word in ("private", "secret", "payload"))


def test_python_module_entrypoint_fails_config_without_traceback_or_secret(tmp_path):
    path = tmp_path / "bad.env"
    path.write_text("DAESINGO_RUNTIME_DB_URL=/private/path-secret\n", encoding="utf-8")
    env = dict(os.environ, DAESINGO_ENV_FILE=str(path), PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "daesingo.worker"],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 1
    assert "runtime.config.invalid" in result.stdout
    assert "Traceback" not in result.stderr
    assert "private" not in result.stdout + result.stderr


def test_dispose_error_is_sanitized_without_replacing_signal_restoration(monkeypatch):
    module = import_module("daesingo.worker.__main__")
    from daesingo.common.logging import configure_logging
    stream, restored = StringIO(), []
    startup = SimpleNamespace(config=SimpleNamespace(db=object()),
                              logger=configure_logging("worker", stream=stream))
    monkeypatch.setattr(module, "bootstrap", lambda **kw: startup)
    def dispose():
        raise RuntimeError("secret /private/path payload")
    monkeypatch.setattr(module, "create_worker_engine", lambda db: SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(module.signal, "getsignal", lambda sig: signal.SIG_DFL)
    monkeypatch.setattr(module.signal, "signal", lambda sig, handler: restored.append(handler))
    monkeypatch.setattr(module, "compose_worker", lambda **kw: SimpleNamespace(run=lambda: None))
    assert module.main() == 1
    assert restored[-2:] == [signal.SIG_DFL, signal.SIG_DFL]
    assert "runtime.worker.cleanup_failed" in stream.getvalue()
    assert all(word not in stream.getvalue() for word in ("secret", "private", "payload"))


@pytest.mark.parametrize("scenario", ["ok", "loop", "cleanup", "both"])
@pytest.mark.parametrize("sink", ["healthy", "filter", "handler"])
def test_main_error_and_cleanup_sink_failures_preserve_exit_and_do_not_disclose(scenario, sink):
    # A real child process detects the otherwise implicit interpreter traceback.
    code = textwrap.dedent("""
        import io, json, signal, sys
        from types import SimpleNamespace
        import daesingo.worker.__main__ as module
        from daesingo.common.logging import configure_logging
        from logging_faults import install_logging_fault
        scenario, sink = sys.argv[1:]
        calls = []
        logger = configure_logging("worker", stream=io.StringIO())
        if sink != "healthy":
            install_logging_fault(logger, sink, lambda name: name.startswith("runtime.worker."))
        startup = SimpleNamespace(config=SimpleNamespace(db=object()), logger=logger)
        module.bootstrap = lambda **kw: startup
        def run():
            calls.append("loop")
            if scenario in ("loop", "both"):
                raise RuntimeError("secret /private/loop user/provider payload")
        def dispose():
            calls.append("dispose")
            if scenario in ("cleanup", "both"):
                raise RuntimeError("secret /private/cleanup user/provider payload")
        module.create_worker_engine = lambda db: SimpleNamespace(dispose=dispose)
        module.compose_worker = lambda **kw: SimpleNamespace(run=run)
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        result = module.main()
        print(json.dumps({"code": result, "calls": calls,
                          "signals_restored": all(signal.getsignal(sig) == handler for sig, handler in previous.items())}))
        raise SystemExit(result)
    """)
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join([str(root / "src"), str(root / "tests")]))
    child = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, scenario, sink],
                           env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert child.stderr == ""
    assert all(word not in child.stdout + child.stderr for word in ("Traceback", "secret", "/private/", "payload"))
    expected = 0 if scenario == "ok" else 1
    assert child.returncode == expected
    assert json.loads(child.stdout) == {"code": expected, "calls": ["loop", "dispose"], "signals_restored": True}
