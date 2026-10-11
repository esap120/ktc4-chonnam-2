import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from daesingo.api.bootstrap import bootstrap as api_bootstrap
from daesingo.worker.bootstrap import bootstrap as worker_bootstrap
from daesingo.common.bootstrap import ModuleFactory


PREFIX = "DAESINGO_RUNTIME_"


def write_env(path, service="api", extra=None):
    values = {
        PREFIX + "DB_URL": "mysql+pymysql://user:secret@localhost/runtime",
        PREFIX + "MEDIA_ROOT": "/private/media",
        PREFIX + service.upper() + "_TEMP_ROOT": "/private/temp",
    }
    if service == "worker":
        values["GEMINI_API_KEY"] = "private-api-key"
    values.update(extra or {})
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()), encoding="utf-8")
    return values


@pytest.mark.parametrize("service,bootstrap", [("api", api_bootstrap), ("worker", worker_bootstrap)])
def test_bootstrap_selects_explicit_file_and_ignores_shell_values(monkeypatch, tmp_path, service, bootstrap):
    env_file = tmp_path / "selected.env"
    write_env(env_file, service)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(env_file))
    monkeypatch.setenv(PREFIX + "DB_POOL_SIZE", "invalid-shell-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "invalid-shell-secret")
    stream = io.StringIO()
    result = bootstrap(revision="test-revision", stream=stream)
    assert result.config.service == service
    assert result.config.db.pool_size == (5 if service == "api" else 2)
    row = json.loads(stream.getvalue())
    assert row["event"] == "process.started" and row["revision"] == "test-revision"
    assert "private" not in stream.getvalue() and "secret" not in stream.getvalue()
    assert "private-api-key" not in repr(result)
    if service == "worker":
        assert result.modules["search"].config.model


def test_bootstrap_reads_file_once_and_passes_same_readonly_mapping_to_factories(monkeypatch, tmp_path):
    import daesingo.common.bootstrap as common_bootstrap
    values = write_env(tmp_path / "api.env")
    calls = []
    mappings = []

    def load(path):
        calls.append(path)
        return values

    def factory(mapping):
        mappings.append(mapping)
        with pytest.raises(TypeError):
            mapping["NEW"] = "value"
        return "validated"

    monkeypatch.setenv("DAESINGO_ENV_FILE", "chosen.env")
    monkeypatch.setattr(common_bootstrap, "load_env_file", load)
    result = api_bootstrap(revision="test", stream=io.StringIO(), module_factories=(
        ModuleFactory("first", ("FIRST_CONFIG",), factory),
        ModuleFactory("second", ("SECOND_CONFIG",), factory),
    ))
    assert calls == ["chosen.env"]
    assert mappings[0] is mappings[1]
    assert dict(result.modules) == {"first": "validated", "second": "validated"}
    with pytest.raises(TypeError):
        result.modules["new"] = "value"


@pytest.mark.parametrize("service,bootstrap", [("api", api_bootstrap), ("worker", worker_bootstrap)])
def test_bootstrap_defaults_to_cwd_env(monkeypatch, tmp_path, service, bootstrap):
    write_env(tmp_path / ".env", service)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DAESINGO_ENV_FILE", raising=False)
    assert bootstrap(revision="test", stream=io.StringIO()).config.service == service


@pytest.mark.parametrize("extra,expected", [
    ({PREFIX + "DB_URL": "private-invalid-url"}, PREFIX + "DB_URL"),
    ({PREFIX + "READY_STORAGE_TIMEOUT_SEC": "2"}, PREFIX + "READY_STORAGE_TIMEOUT_SEC"),
    ({PREFIX + "CLEANUP_STAGING_AGE_SEC": "3599"}, PREFIX + "CLEANUP_STAGING_AGE_SEC"),
    ({PREFIX + "READY_DB_TIMEOUT_SEC": "2.1"}, PREFIX + "READY_DB_TIMEOUT_SEC"),
    ({PREFIX + "LOG_LEVEL": "private-invalid-level"}, PREFIX + "LOG_LEVEL"),
])
def test_config_failure_logs_only_keys_and_exits(monkeypatch, tmp_path, extra, expected):
    path = tmp_path / "api.env"
    write_env(path, extra=extra)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    stream = io.StringIO()
    with pytest.raises(SystemExit) as error:
        api_bootstrap(revision="test", stream=stream)
    assert error.value.code == 1
    row = json.loads(stream.getvalue())
    assert row["event"] == "runtime.config.invalid"
    assert expected in row["keys"]
    assert "private" not in stream.getvalue() and "secret" not in stream.getvalue()


def test_module_factory_exception_is_sanitized(monkeypatch, tmp_path):
    path = tmp_path / "api.env"
    write_env(path)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))

    def fail(mapping):
        raise ValueError("private token from provider /private/path")

    stream = io.StringIO()
    with pytest.raises(SystemExit):
        api_bootstrap(revision="test", stream=stream, module_factories=(
            ModuleFactory("example", ("EXAMPLE_API_KEY",), fail),
        ))
    row = json.loads(stream.getvalue())
    assert row["event"] == "runtime.config.invalid" and row["keys"] == ["EXAMPLE_API_KEY"]
    assert "private" not in stream.getvalue()


@pytest.mark.parametrize("extra,key", [
    ({"GEMINI_API_KEY": ""}, "GEMINI_API_KEY"),
    ({"DAESINGO_GEMINI_INPUT_USD_PER_MILLION": "private-invalid"}, "DAESINGO_GEMINI_INPUT_USD_PER_MILLION"),
    ({"DAESINGO_GEMINI_BASE_URL": "http://private.invalid"}, "DAESINGO_GEMINI_BASE_URL"),
])
def test_worker_validates_real_search_config_at_startup(monkeypatch, tmp_path, extra, key):
    path = tmp_path / "worker.env"
    write_env(path, "worker", extra)
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    stream = io.StringIO()
    with pytest.raises(SystemExit):
        worker_bootstrap(revision="test", stream=stream)
    assert key in json.loads(stream.getvalue())["keys"]
    assert "private" not in stream.getvalue()


def test_unknown_runtime_key_warns_even_at_error_level(monkeypatch, tmp_path):
    path = tmp_path / "api.env"
    write_env(path, extra={PREFIX + "TYPO": "private-value", PREFIX + "LOG_LEVEL": "ERROR"})
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    stream = io.StringIO()
    api_bootstrap(revision="test", stream=stream)
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(row["event"] == "runtime.config.unknown" and row["keys"] == [PREFIX + "TYPO"] for row in rows)
    assert "private" not in stream.getvalue()


@pytest.mark.parametrize("failure", ["missing", "unreadable", "invalid-encoding"])
def test_file_errors_do_not_expose_path(monkeypatch, tmp_path, failure):
    path = tmp_path / "private.env"
    if failure == "unreadable":
        path.mkdir()
    elif failure == "invalid-encoding":
        path.write_bytes(b"\xff")
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    stream = io.StringIO()
    with pytest.raises(SystemExit):
        api_bootstrap(revision="test", stream=stream)
    assert "private" not in stream.getvalue()
    assert json.loads(stream.getvalue())["event"] == "runtime.config.invalid"


@pytest.mark.parametrize("service", ["api", "worker"])
def test_bootstrap_process_exits_nonzero_without_exception_values(tmp_path, service):
    path = tmp_path / "private.env"
    write_env(path, service, {PREFIX + "DB_URL": "private-invalid-url"})
    env = os.environ.copy()
    env["DAESINGO_ENV_FILE"] = str(path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    process = subprocess.run(
        [sys.executable, "-c", f"from daesingo.{service}.bootstrap import bootstrap; bootstrap(revision='test')"],
        capture_output=True, text=True, env=env, check=False,
    )
    assert process.returncode == 1
    assert process.stderr == ""
    assert json.loads(process.stdout)["event"] == "runtime.config.invalid"
    assert "private" not in process.stdout
