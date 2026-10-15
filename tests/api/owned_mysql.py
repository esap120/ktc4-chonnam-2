"""A disposable second server for actual SHUTDOWN acceptance, never suite DB."""
from contextlib import contextmanager
import os
import shlex
import socket
import subprocess
import sys
import time
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool


def shutdown(url):
    engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT",
                           connect_args={"connect_timeout": 1, "read_timeout": 2})
    try:
        with engine.connect() as conn:
            try:
                conn.exec_driver_sql("SHUTDOWN")
            except Exception:
                # SHUTDOWN can close its own connection; verify port below.
                pass
            finally:
                conn.invalidate()  # No rollback on an intentionally closed server.
    finally:
        engine.dispose()


@contextmanager
def owned_mysql():
    name = "rt08a-stop-" + uuid4().hex
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = "/tmp/" + name
    container = None
    url = URL.create("mysql+pymysql", username="root", host="127.0.0.1", port=port,
                     database="rt08a_stop_test")
    try:
        if sys.platform == "win32":
            binpath = os.environ["DAESINGO_MYSQL_TEST_BASEDIR"]
            libpath = os.environ["DAESINGO_MYSQL_TEST_LIBDIR"]
            script = f"""set -eu
export LD_LIBRARY_PATH={shlex.quote(libpath)}
bin={shlex.quote(binpath)}
base={shlex.quote(base)}
mkdir -p "$base/data"
"$bin/bin/mysqld" --no-defaults --initialize-insecure --user="$(id -un)" --basedir="$bin" --datadir="$base/data" --log-error="$base/init.log"
printf 'CREATE DATABASE rt08a_stop_test;\n' > "$base/init.sql"
"$bin/bin/mysqld" --no-defaults --daemonize --user="$(id -un)" --basedir="$bin" --datadir="$base/data" --port={port} --bind-address=127.0.0.1 --mysqlx=OFF --socket="$base/mysql.sock" --pid-file="$base/server.pid" --log-error="$base/server.log" --init-file="$base/init.sql"
"""
            subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "sh"], input=script.encode(),
                           capture_output=True, check=True, timeout=60)
        else:
            # GitHub's service has already pulled this image. A second container
            # isolates SHUTDOWN from every existing MySQL acceptance obligation.
            subprocess.run(["docker", "run", "--detach", "--name", name,
                            "--publish", f"127.0.0.1:{port}:3306", "--env", "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
                            "--env", "MYSQL_ROOT_HOST=%", "--env", "MYSQL_DATABASE=rt08a_stop_test", "mysql:8.4"],
                           capture_output=True, check=True, timeout=60)
            container = name
        deadline = time.monotonic() + 60
        while True:
            engine = create_engine(url, poolclass=NullPool,
                                   connect_args={"connect_timeout": 1, "read_timeout": 2})
            try:
                with engine.connect() as conn:
                    assert conn.exec_driver_sql("SELECT VERSION()").scalar_one().startswith("8.4.")
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise AssertionError("owned MySQL 8.4 startup failed") from None
                time.sleep(.2)
            finally:
                engine.dispose()
        yield url
    finally:
        try:
            shutdown(url)
        except Exception:
            pass
        if container:
            subprocess.run(["docker", "rm", "--force", container], check=True, capture_output=True, timeout=30)
        if sys.platform == "win32":
            # Fixed /tmp prefix + generated UUID; no arbitrary recursive paths.
            script = f"""set -eu
base={shlex.quote(base)}
case "$base" in /tmp/rt08a-stop-*) ;; *) exit 1;; esac
if test -f "$base/server.pid"; then
  pid=$(cat "$base/server.pid")
  kill "$pid" 2>/dev/null || true
  for i in $(seq 1 100); do test ! -e "$base/server.pid" && break; sleep .1; done
fi
test ! -e "$base/server.pid"
rm -rf -- "$base"
"""
            subprocess.run(["wsl.exe", "-d", "Ubuntu", "--", "sh"], input=script.encode(),
                           capture_output=True, check=True, timeout=30)
        assert_port_closed(port)


def assert_port_closed(port):
    # An automatically chosen source equal to the destination can establish a
    # TCP self-connection even with no listener. Reserve that candidate while
    # selecting a different source; keep the real-listener assertion and budget.
    with socket.socket() as candidate, socket.socket() as alternate:
        candidate.bind(("127.0.0.1", 0))
        probe = candidate
        if candidate.getsockname()[1] == port:
            alternate.bind(("127.0.0.1", 0))
            probe = alternate
        probe.settimeout(1)
        assert probe.connect_ex(("127.0.0.1", port)) != 0, "owned MySQL port remains open"
