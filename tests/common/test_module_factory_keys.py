import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from daesingo.api.bootstrap import bootstrap as api_bootstrap
from daesingo.common.bootstrap import ModuleFactory
from daesingo.worker.bootstrap import bootstrap as worker_bootstrap


INVALID_KEYS = [
    ("EXAMPLE_API_KEY", None),
    ("EXAMPLE_API_KEY", 7),
    ("EXAMPLE_API_KEY", {"unhashable": "private-secret"}),
    ("bad-key",),
    ("private-secret C:\\private\\credential.env\n",),
    None,
    "EXAMPLE_API_KEY",
]
INVALID_IDS = ["none-entry", "integer-entry", "unhashable-entry", "bad-format",
               "sensitive-entry", "none-container", "string-container"]


def write_env(path, service):
    path.write_text("\n".join([
        "DAESINGO_RUNTIME_DB_URL=mysql+pymysql://test:test@localhost/runtime",
        "DAESINGO_RUNTIME_MEDIA_ROOT=/runtime/media",
        f"DAESINGO_RUNTIME_{service.upper()}_TEMP_ROOT=/runtime/temp",
        "GEMINI_API_KEY=test-key",
    ]), encoding="utf-8")


@pytest.mark.parametrize("keys", INVALID_KEYS, ids=INVALID_IDS)
@pytest.mark.parametrize("service,bootstrap", [("api", api_bootstrap), ("worker", worker_bootstrap)])
def test_invalid_factory_keys_stop_all_factories_safely(monkeypatch, tmp_path, capsys, keys, service, bootstrap):
    path = tmp_path / "runtime.env"
    write_env(path, service)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    calls = []

    def earlier_factory(mapping):
        calls.append("earlier")
        return "valid"

    def failing_factory(mapping):
        calls.append("invalid")
        raise RuntimeError("private-secret C:\\private\\credential.env")

    stream = io.StringIO()
    with pytest.raises(SystemExit) as error:
        bootstrap(revision="test", stream=stream, module_factories=(
            ModuleFactory("earlier", ("EARLIER_CONFIG",), earlier_factory),
            ModuleFactory("example", keys, failing_factory),
        ))
    assert error.value.code == 1
    assert calls == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    row = json.loads(stream.getvalue())
    assert row["event"] == "runtime.config.invalid"
    assert row["keys"] == []
    assert row["status"] == "INVALID_MODULE_FACTORY_KEYS"
    for forbidden in ("private-secret", "private", "credential.env", "bad-key", "Traceback"):
        assert forbidden not in stream.getvalue()


@pytest.mark.parametrize("keys", INVALID_KEYS, ids=INVALID_IDS)
def test_factory_key_failures_exit_process_without_traceback(tmp_path, keys):
    path = tmp_path / "runtime.env"
    write_env(path, "api")
    env = os.environ.copy()
    env["DAESINGO_ENV_FILE"] = str(path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    script = "\n".join([
        "from daesingo.api.bootstrap import bootstrap",
        "from daesingo.common.bootstrap import ModuleFactory",
        "def fail(mapping):",
        "    print('FACTORY_EXECUTED')",
        "    raise RuntimeError('private-secret C:\\\\private\\\\credential.env')",
        f"bootstrap(revision='test', module_factories=(ModuleFactory('example', {keys!r}, fail),))",
    ])
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert result.stderr == ""
    row = json.loads(result.stdout)
    assert row["event"] == "runtime.config.invalid" and row["keys"] == []
    assert row["status"] == "INVALID_MODULE_FACTORY_KEYS"
    for forbidden in ("FACTORY_EXECUTED", "private", "credential.env", "bad-key", "Traceback"):
        assert forbidden not in result.stdout


def test_valid_factory_keys_sanitize_exception_in_process(tmp_path):
    path = tmp_path / "runtime.env"
    write_env(path, "api")
    env = os.environ.copy()
    env["DAESINGO_ENV_FILE"] = str(path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    script = "\n".join([
        "from daesingo.api.bootstrap import bootstrap",
        "from daesingo.common.bootstrap import ModuleFactory",
        "def fail(mapping):",
        "    raise RuntimeError('private-secret C:\\\\private\\\\credential.env')",
        "bootstrap(revision='test', module_factories=(ModuleFactory('example', ('EXAMPLE_API_KEY',), fail),))",
    ])
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1 and result.stderr == ""
    row = json.loads(result.stdout)
    assert row["event"] == "runtime.config.invalid" and row["keys"] == ["EXAMPLE_API_KEY"]
    assert "private" not in result.stdout and "Traceback" not in result.stdout
