"""HTTP contract boundaries: fail on leaked detail, wrong status, dependency work in live."""
import json
import socket
from threading import Event
from time import monotonic

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from daesingo.api.app import create_app
from daesingo.api.health import Readiness, storage_available
from daesingo.common.config import ReadySettings
from daesingo.common.db.errors import BeforeCommitFailure, CommitOutcomeUnknown


def envelope(code):
    return {"ok": False, "error": {"code": code, "message_key": code}, "case_view": None}


def test_live_unknown_methods_and_unpublished_surfaces(api_startup, monkeypatch):
    startup, stream = api_startup
    app = create_app(startup=startup)
    def forbidden(*args, **kwargs):
        raise AssertionError("network/provider called")
    import pymysql, httpx
    monkeypatch.setattr(pymysql.connections.Connection, "connect", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "ok"}
        for path in ("/missing?secret=private", "/docs", "/openapi.json", "/health/live/", "/cases", "/jobs"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 404
            assert response.json() == envelope("http.not_found")
        response = client.post("/health/live")
        assert response.status_code == 405
        assert response.json() == envelope("http.method_not_allowed")
        assert response.headers["allow"] == "GET"
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    access = [e for e in events if e["event"] == "api.request.completed"]
    assert len(access) == 8
    assert all(e["trace_id"].startswith("tr_") and e["duration_ms"] >= 0 for e in access)
    assert len({e["trace_id"] for e in access}) == 8
    assert "secret" not in stream.getvalue() and "private" not in stream.getvalue()


@pytest.mark.parametrize("error,status,code", [
    (BeforeCommitFailure("pool_timeout"), 503, "http.dependency_unavailable"),
    (CommitOutcomeUnknown(), 500, "http.internal_error"),
    (RuntimeError("private /path SQL password"), 500, "http.internal_error"),
    (HTTPException(404, detail="private", headers={"x-secret": "private"}), 404, "http.not_found"),
    (HTTPException(422, detail="private"), 500, "http.internal_error"),
])
def test_failures_are_safe(api_startup, error, status, code):
    startup, stream = api_startup
    app = create_app(startup=startup)
    @app.get("/test-error")
    def fail():
        raise error
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error", headers={"x-trace-id": "private"})
        assert response.status_code == status
        assert response.json() == envelope(code)
        assert "x-secret" not in response.headers
    assert "private" not in stream.getvalue()
    assert '"event":"api.request.failed"' in stream.getvalue()
    assert '"event":"api.request.completed"' in stream.getvalue()


def test_transport_validation_uses_envelope(api_startup):
    startup, stream = api_startup
    app = create_app(startup=startup)
    class Input(BaseModel):
        count: int
    @app.post("/test-validation/{number}")
    def validate(number: int, body: Input):
        return {"number": number}
    with TestClient(app) as client:
        for path, body in (("/test-validation/private", {"count": 1}),
                           ("/test-validation/1", {"count": "private"})):
            response = client.post(path, json=body)
            assert response.status_code == 400
            assert response.json() == envelope("http.malformed_request")
    assert "private" not in stream.getvalue()


@pytest.mark.parametrize("mode", ["ok", "missing", "file"])
def test_storage_metadata_only(tmp_path, mode):
    root = tmp_path / "media"
    if mode == "ok":
        root.mkdir()
    elif mode == "file":
        root.write_text("test")
    before = sorted(tmp_path.rglob("*"))
    assert storage_available(root) is (mode == "ok")
    assert sorted(tmp_path.rglob("*")) == before


@pytest.mark.parametrize("dependency", ["db", "storage"])
def test_deadline_no_accumulating_threads_and_late_recovery(api_startup, dependency):
    startup, stream = api_startup
    entered, release, finished = Event(), Event(), Event()
    calls = []
    def slow():
        calls.append(1); entered.set()
        release.wait(2); finished.set()
        return True
    ready = Readiness(settings=ReadySettings(db_timeout_sec=.06, storage_timeout_sec=.06),
                      db_probe=slow if dependency == "db" else lambda: True,
                      storage_probe=slow if dependency == "storage" else lambda: True,
                      logger=startup.logger)
    try:
        start = monotonic()
        assert not ready.check()
        assert entered.is_set()
        assert monotonic() - start < .4
        assert not ready.check()
        assert calls == [1]
    finally:
        release.set(); assert finished.wait(1)
        ready.close()
    assert dependency in stream.getvalue()


def test_closed_and_dependency_failure_are_unavailable(api_startup):
    startup, stream = api_startup
    def fail():
        raise RuntimeError("secret /internal/path")
    ready = Readiness(settings=ReadySettings(), db_probe=fail,
                      storage_probe=lambda: True, logger=startup.logger)
    assert not ready.check()
    ready.close()
    assert not ready.check()
    assert "secret" not in stream.getvalue()


def test_bootstrap_fails_before_serving_and_reads_file(api_startup, tmp_path, monkeypatch):
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(tmp_path / "missing.env"))
    with pytest.raises(SystemExit) as error:
        create_app(revision="test")
    assert error.value.code == 1
    env = tmp_path / "runtime.env"
    env.write_text("DAESINGO_RUNTIME_DB_URL=mysql+pymysql://test@127.0.0.1:1/api_test\n"
                   f"DAESINGO_RUNTIME_MEDIA_ROOT={tmp_path}\nDAESINGO_RUNTIME_API_TEMP_ROOT={tmp_path}\n")
    monkeypatch.setenv("DAESINGO_ENV_FILE", str(env))
    app = create_app(revision="test")
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}


def test_launch_workers_one_and_no_unsafe_uvicorn_logs(monkeypatch):
    from daesingo.api.__main__ import main
    received = {}
    monkeypatch.setenv("WEB_CONCURRENCY", "9")
    monkeypatch.setattr("daesingo.api.__main__.create_app", lambda **kwargs: "app")
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: received.update(app=app, **kwargs))
    main(["--revision", "test", "--host", "127.0.0.1", "--port", "8123"])
    assert received["workers"] == 1 and received["reload"] is False
    assert received["access_log"] is False and received["log_config"] is None
    assert received["port"] == 8123


@pytest.mark.parametrize("status", [200, 404, 500])
def test_structured_sink_failure_does_not_change_http_outcome(api_startup, status):
    startup, stream = api_startup
    app = create_app(startup=startup)
    @app.get("/test-log-fault")
    def fail():
        raise RuntimeError("private")
    def broken(record):
        raise RuntimeError("private logging sink")
    startup.logger.addFilter(broken)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            path = {200: "/health/live", 404: "/missing", 500: "/test-log-fault"}[status]
            assert client.get(path).status_code == status
    finally:
        startup.logger.removeFilter(broken)
    assert "private" not in stream.getvalue()


def test_concurrent_ready_calls_share_successful_inflight_probe(api_startup):
    from threading import Thread
    startup, stream = api_startup
    entered, release = Event(), Event()
    calls = []
    def db():
        calls.append(1); entered.set(); release.wait(1); return True
    ready = Readiness(settings=ReadySettings(), db_probe=db,
                      storage_probe=lambda: True, logger=startup.logger)
    results = []
    first = Thread(target=lambda: results.append(ready.check()))
    second = Thread(target=lambda: results.append(ready.check()))
    try:
        first.start(); assert entered.wait(1)
        second.start()
        # Let the second caller wait on the current healthy probe.
        from time import sleep
        sleep(.03); release.set()
        first.join(1); second.join(1)
        assert results == [True, True]
        assert calls == [1]
    finally:
        release.set(); first.join(1); second.join(1); ready.close()


def test_server_exception_logger_cannot_emit_private_traceback(monkeypatch):
    import logging
    from io import StringIO
    from daesingo.api.__main__ import main
    output = StringIO()
    logger = logging.getLogger("uvicorn.error")
    monkeypatch.setattr(logger, "handlers", [logging.StreamHandler(output)])
    monkeypatch.setattr(logger, "propagate", False)
    monkeypatch.setattr("daesingo.api.__main__.create_app", lambda **kwargs: "app")
    def run(app, **kwargs):
        try:
            raise RuntimeError("PRIVATE_INTERNAL_PATH")
        except RuntimeError:
            logger.error("ASGI application error", exc_info=True)
    monkeypatch.setattr("uvicorn.run", run)
    main(["--revision", "test"])
    assert output.getvalue() == ""


def test_slow_log_sink_cannot_hold_ready_response(api_startup):
    from threading import Thread
    startup, stream = api_startup
    entered, release, done = Event(), Event(), Event()
    def slow(record):
        entered.set(); release.wait(8); return True
    startup.logger.addFilter(slow)
    ready = Readiness(settings=ReadySettings(), db_probe=lambda: True,
                      storage_probe=lambda: True, logger=startup.logger)
    result = []
    thread = Thread(target=lambda: (result.append(ready.check()), done.set()))
    try:
        thread.start(); assert entered.wait(1)
        assert done.wait(3.3), "log sink exceeded readiness response budget"
        assert result == [True]
    finally:
        release.set(); thread.join(2); ready.close(); startup.logger.removeFilter(slow)


def test_composition_failure_exits_without_input_or_traceback(tmp_path):
    import subprocess, sys, os
    runtime = tmp_path / "unsafe.env"
    runtime.write_text("DAESINGO_RUNTIME_DB_URL=mysql+pymysql://test:secret@127.0.0.1:1/test?local_infile=PRIVATE_QUERY_VALUE\n"
        f"DAESINGO_RUNTIME_MEDIA_ROOT={tmp_path}\nDAESINGO_RUNTIME_API_TEMP_ROOT={tmp_path}\n")
    result = subprocess.run([sys.executable, "-B", "-m", "daesingo.api", "--revision", "test"],
        env=dict(os.environ, DAESINGO_ENV_FILE=str(runtime)), capture_output=True, timeout=10)
    assert result.returncode == 1
    assert b"private" not in (result.stdout + result.stderr).lower()
    assert b"Traceback" not in result.stdout + result.stderr
    assert b"api.composition.failed" in result.stdout


def test_event_thread_start_failure_is_isolated(api_startup, monkeypatch):
    from threading import Thread
    from daesingo.api.events import ApiEvents
    startup, stream = api_startup
    class FailedThread(Thread):
        def start(self):
            raise RuntimeError("private thread failure")
    monkeypatch.setattr("daesingo.api.events.Thread", FailedThread)
    events = ApiEvents(startup.logger)
    events.emit("api.request.completed", status="200")
    events.close()
    assert "private" not in stream.getvalue()


def test_bounded_events_capture_request_context_before_drain(api_startup):
    from daesingo.api.events import ApiEvents
    from daesingo.common.logging import bind_context
    startup, stream = api_startup
    entered, release = Event(), Event()
    def slow(record):
        entered.set(); release.wait(2); return True
    startup.logger.addFilter(slow)
    events = ApiEvents(startup.logger)
    try:
        with bind_context(trace_id="tr_one"):
            events.emit("api.request.completed", status="200")
        assert entered.wait(1)
        with bind_context(trace_id="tr_two"):
            for _ in range(160):
                events.emit("api.request.completed", status="200")
        release.set(); events.close()
        records = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert records[0]["trace_id"] == "tr_one"
        assert all(record["trace_id"] == "tr_two" for record in records[1:])
        assert 1 < len(records) <= 129
    finally:
        release.set(); events.close(); startup.logger.removeFilter(slow)
