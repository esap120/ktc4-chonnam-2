import io
import json

import pytest

from daesingo.worker.bootstrap import bootstrap


@pytest.mark.parametrize("suffix,value", [
    ("HEARTBEAT_INTERVAL_SEC", "0"),
    ("LEASE_DURATION_SEC", "10"),
    ("STALE_SWEEP_INTERVAL_SEC", "0"),
    ("HEARTBEAT_DB_CONNECT_TIMEOUT_SEC", "0"),
    ("HEARTBEAT_DB_READ_TIMEOUT_SEC", "2"),
    ("HEARTBEAT_DB_WRITE_TIMEOUT_SEC", "0"),
    ("DB_LOCK_WAIT_TIMEOUT_SEC", "10"),
])
def test_worker_baseline_invariants_fail_startup_without_values(monkeypatch, tmp_path, suffix, value):
    key = "DAESINGO_RUNTIME_" + suffix
    path = tmp_path / "worker.env"
    path.write_text("\n".join([
        "DAESINGO_RUNTIME_DB_URL=mysql+pymysql://user:private-secret@localhost/runtime",
        "DAESINGO_RUNTIME_MEDIA_ROOT=/private/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT=/private/worker",
        "GEMINI_API_KEY=private-secret",
        f"{key}={value}",
    ]), encoding="utf-8")
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(path))
    stream = io.StringIO()
    with pytest.raises(SystemExit) as error:
        bootstrap(revision="test", stream=stream)
    assert error.value.code == 1
    row = json.loads(stream.getvalue())
    assert row["event"] == "runtime.config.invalid" and key in row["keys"]
    assert "private" not in stream.getvalue()
