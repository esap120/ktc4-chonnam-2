"""Real MySQL health acceptance: shared pool must never gate readiness."""
from dataclasses import replace
import json
import os
from time import monotonic
from types import MappingProxyType

import pytest
from fastapi.testclient import TestClient
from daesingo.api.app import create_app
from daesingo.common.bootstrap import Startup
from daesingo.common.config import DbSettings
from daesingo.common.db.transactions import run_api_transaction
from mysql_fault_proxy import CommitResponseProxy

pytestmark = pytest.mark.mysql


def build(startup, url):
    return replace(startup, config=replace(startup.config, db=DbSettings(
        url=url.render_as_string(hide_password=False), pool_size=1, max_overflow=0, pool_timeout_sec=.05)))


@pytest.mark.mysql_check("api_health", "ready", parameter="normal")
@pytest.mark.mysql_check("api_health", "ready", parameter="pool_exhausted")
def test_ready_uses_real_mysql_dedicated_connection(api_startup, mysql_schema_url, monkeypatch):
    startup, stream = api_startup
    app = create_app(startup=build(startup, mysql_schema_url))
    def forbidden(*args, **kwargs):
        raise AssertionError("provider HTTP called")
    # Only HTTP provider transports forbidden; PyMySQL sockets remain real.
    import httpx
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    with TestClient(app) as client:
        assert client.get("/health/ready").json() == {"status": "ok"}
        with app.state.composition.engine.connect():
            start = monotonic()
            response = client.get("/health/ready")
            assert response.status_code == 200 and response.json() == {"status": "ok"}
            assert monotonic() - start < 3.5
            @app.get("/test-pool")
            def checkout():
                return run_api_transaction(app.state.composition.engine, lambda conn: {})
            response = client.get("/test-pool")
            assert response.status_code == 503
            assert response.json() == {"ok": False, "error": {"code": "http.dependency_unavailable",
                "message_key": "http.dependency_unavailable"}, "case_view": None}
    assert app.state.composition.engine.pool.checkedout() == 0
    assert '"event":"api.ready.completed"' in stream.getvalue()
    assert str(mysql_schema_url.database) not in stream.getvalue()


@pytest.mark.mysql_check("api_health", "ready", parameter="connection_lost")
def test_ready_fails_after_real_mysql_transport_stops(api_startup, mysql_schema_url):
    startup, stream = api_startup
    with CommitResponseProxy(mysql_schema_url.host, mysql_schema_url.port or 3306, drop_commits=0) as proxy:
        url = mysql_schema_url.set(host="127.0.0.1", port=proxy.port).update_query_dict({"ssl_disabled": "true"})
        app = create_app(startup=build(startup, url))
        with TestClient(app) as client:
            assert client.get("/health/ready").status_code == 200
    app = create_app(startup=build(startup, url))
    with TestClient(app) as client:
        start = monotonic()
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.json() == {"status": "unavailable"}
        assert monotonic() - start < 3.5
        assert client.get("/health/live").json() == {"status": "ok"}
    assert "password" not in stream.getvalue()


@pytest.mark.mysql_check("api_health", "storage", parameter="readonly")
def test_ready_rejects_actual_readonly_linux_mount(api_startup, mysql_schema_url):
    # A private namespace holds an actual RO tmpfs; no host mount changes.
    import subprocess, sys
    from pathlib import Path
    startup, stream = api_startup
    script = Path(__file__).with_name("readonly_probe.py")
    command = (["wsl.exe", "-d", "Ubuntu", "-u", "root", "--", "unshare", "--mount",
                "--propagation", "private", "python3", "/mnt/c/ktc4-chonnam-2/tests/api/readonly_probe.py"]
               if sys.platform == "win32" else
               ["sudo", "-n", "unshare", "--mount", "--propagation", "private", sys.executable, str(script)])
    def actual_mount_probe():
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        evidence = json.loads(result.stdout)
        assert evidence == {"readonly": True, "available": False}
        return evidence["available"]
    assert actual_mount_probe() is False
    app = create_app(startup=build(startup, mysql_schema_url))
    app.state.composition.readiness.storage_probe = actual_mount_probe
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.json() == {"status": "unavailable"}
    assert '"event":"api.ready.storage.unavailable"' in stream.getvalue()


@pytest.mark.mysql_check("api_health", "ready", parameter="server_stopped")
def test_ready_when_actual_mysql_server_is_shutdown(api_startup, mysql_server_url):
    from owned_mysql import owned_mysql, shutdown
    startup, stream = api_startup
    with owned_mysql() as url:
        app = create_app(startup=build(startup, url))
        with TestClient(app) as client:
            assert client.get("/health/ready").status_code == 200
            shutdown(url)
            start = monotonic()
            response = client.get("/health/ready")
            assert response.status_code == 503 and response.json() == {"status": "unavailable"}
            assert monotonic() - start < 3.5
            assert client.get("/health/live").status_code == 200
    assert '"event":"api.ready.db.unavailable"' in stream.getvalue()


@pytest.mark.mysql_check("api_health", "process", parameter="single_worker")
def test_actual_api_process_and_clean_shutdown(api_startup, mysql_schema_url, tmp_path):
    import socket, subprocess, sys, time
    import urllib.request
    import urllib.error
    startup, stream = api_startup
    runtime_file = tmp_path / "api.env"
    runtime_file.write_text("DAESINGO_RUNTIME_DB_URL=" + mysql_schema_url.render_as_string(hide_password=False)
        + "\nDAESINGO_RUNTIME_MEDIA_ROOT=" + str(tmp_path)
        + "\nDAESINGO_RUNTIME_API_TEMP_ROOT=" + str(tmp_path) + "\n")
    env = dict(os.environ, DAESINGO_ENV_FILE=str(runtime_file), WEB_CONCURRENCY="9")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-B", "-m", "daesingo.api", "--revision", "test",
                                "--host", "127.0.0.1", "--port", str(port)],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 15
        def get(path):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}" + path, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        while True:
            assert process.poll() is None, "API process exited at startup"
            try:
                if get("/health/live") == (200, {"status": "ok"}):
                    break
            except (urllib.error.URLError, OSError):
                pass
            assert time.monotonic() < deadline, "API listener startup deadline"
            time.sleep(.05)
        assert get("/health/ready") == (200, {"status": "ok"})
        assert get("/private-path?token=private")[0] == 404
    finally:
        process.terminate()
        out, err = process.communicate(timeout=15)
    assert b"private" not in out + err
    events = [json.loads(line) for line in out.splitlines()]
    assert len([e for e in events if e["event"] == "process.started"]) == 1
    assert any(e["event"] == "api.request.completed" for e in events)
    with socket.socket() as sock:
        sock.settimeout(1)
        assert sock.connect_ex(("127.0.0.1", port)) != 0
