"""Shared, opt-in real MySQL harness. Existing Case fixtures remain untouched.

DAESINGO_MYSQL_URL must point to a disposable database whose name contains 'test'.
The account needs CREATE/DROP DATABASE for per-test schemas and KILL of its own
connections. CI uses a disposable MySQL 8.4 service, never a production server.
The negative-permission integration test additionally needs CREATE USER,
GRANT SELECT (GRANT OPTION), and DROP USER; use a disposable admin test account
for the complete acceptance suite, never application credentials.
"""

from contextlib import contextmanager
import importlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest


# Only transport/encoding/I/O options that cannot select a different endpoint,
# account or schema. SQLAlchemy merges query over URL path connect arguments;
# PyMySQL also accepts db, init_command and read_default_* aliases. Unknown
# options fail closed, including future driver initialization escape paths.
_SAFE_QUERY_OPTIONS = frozenset({
    "charset", "use_unicode", "binary_prefix", "connect_timeout", "read_timeout",
    "write_timeout", "ssl_ca", "ssl_cert", "ssl_key", "ssl_capath", "ssl_cipher",
    "ssl_key_password", "ssl_verify_cert", "ssl_verify_identity",
    "ssl_check_hostname", "ssl_disabled", "server_public_key", "program_name",
})


def _validate_query(url):
    if set(url.query) - _SAFE_QUERY_OPTIONS:
        raise pytest.UsageError("MySQL test URL query options are not permitted") from None


def _dependency_check():
    for name in ("sqlalchemy", "pymysql", "alembic"):
        try:
            importlib.import_module(name)
        except ImportError:
            raise pytest.UsageError(f"MySQL required dependency unavailable: {name}") from None


def _test_url():
    value = os.environ.get("DAESINGO_MYSQL_URL")
    if not value:
        raise pytest.UsageError("DAESINGO_REQUIRE_MYSQL=1 requires DAESINGO_MYSQL_URL")
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError
    try:
        url = make_url(value)
        if (url.drivername != "mysql+pymysql" or not url.host or not url.username
                or not url.database or "test" not in url.database.lower()):
            raise ValueError
        _validate_query(url)
        return url
    except (ValueError, TypeError, ArgumentError):
        raise pytest.UsageError("MySQL URL must identify a disposable mysql+pymysql test database") from None


def _control_engine(url):
    _validate_query(url)
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    return create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT", hide_parameters=True,
                         connect_args={"connect_timeout": 2, "read_timeout": 5, "write_timeout": 5})


@contextmanager
def _schema(engine):
    _validate_query(engine.url)
    # Only delete the exact schema successfully created by this fixture.
    name = "rt02a_test_" + uuid4().hex
    with engine.connect() as conn:
        conn.exec_driver_sql(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
    try:
        yield name
    finally:
        with engine.connect() as conn:
            conn.exec_driver_sql(f"DROP DATABASE `{name}`")


def _preflight():
    _dependency_check()
    engine = None
    try:
        engine = _control_engine(_test_url())
        with engine.connect() as conn:
            version = conn.exec_driver_sql("SELECT VERSION()").scalar_one()
            if not version.startswith("8.4."):
                raise pytest.UsageError("MySQL integration requires real MySQL 8.4")
        with _schema(engine):
            pass  # privilege errors must fail even before Case's opt-in fixture
        return version
    except pytest.UsageError:
        raise
    except Exception:
        raise pytest.UsageError("MySQL preflight failed (connection/schema privileges); no skip fallback") from None
    finally:
        if engine is not None:
            engine.dispose()


def pytest_addoption(parser):
    parser.addoption("--mysql-report", help="Write MySQL collection/execution evidence JSON")


def pytest_configure(config):
    _collection_problems.clear()
    # Case's unchanged child fixture creates its own engine. Validate even in
    # local opt-in mode, before collection can reach any owner fixture's DDL.
    if os.environ.get("DAESINGO_MYSQL_URL"):
        _test_url()
    config._mysql_evidence = {"server_version": None, "collected": [], "selected": [],
                              "reports": [], "collection_errors": []}
    config._mysql_nodes = set()
    if os.environ.get("DAESINGO_REQUIRE_MYSQL") == "1":
        config._mysql_evidence["server_version"] = _preflight()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        path = item.nodeid.split("::")[0].replace("\\", "/")
        callspec = getattr(item, "callspec", None)
        legacy = path == "tests/case/test_store_mysql.py" or (
            path == "tests/case/test_case_repository_contract.py" and callspec is not None
            and callspec.params.get("repo_conn") == "mysql")
        if legacy:
            item.add_marker(pytest.mark.mysql)
        if item.get_closest_marker("mysql"):
            from _pytest.junitxml import mangle_test_address
            address = mangle_test_address(item.nodeid)
            checks = []
            for mark in item.iter_markers("mysql_check"):
                if len(mark.args) != 2 or not all(isinstance(value, str) for value in mark.args):
                    raise pytest.UsageError("Invalid MySQL role/scenario marker")
                check = {"role": mark.args[0], "scenario": mark.args[1]}
                if mark.kwargs:
                    if (set(mark.kwargs) != {"parameter"} or
                            not isinstance(mark.kwargs["parameter"], str) or not mark.kwargs["parameter"]):
                        raise pytest.UsageError("Invalid MySQL parameter marker")
                    check["parameter"] = mark.kwargs["parameter"]
                checks.append(check)
            config._mysql_nodes.add(item.nodeid)
            config._mysql_evidence["collected"].append({
                "nodeid": item.nodeid, "junit": [".".join(address[:-1]), address[-1]],
                "scenarios": [value for mark in item.iter_markers("mysql_scenario") for value in mark.args],
                "checks": checks,
            })


def pytest_collection_finish(session):
    session.config._mysql_evidence["selected"] = [
        item.nodeid for item in session.items if item.nodeid in session.config._mysql_nodes]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if item.nodeid in item.config._mysql_nodes:
        item.config._mysql_evidence["reports"].append({
            "nodeid": item.nodeid, "when": report.when, "outcome": report.outcome,
            "xfail": hasattr(report, "wasxfail"),
        })


def pytest_collectreport(report):
    # Collection skips (including importorskip) occur before item markers exist.
    # Require mode imports DB dependencies; unrelated opt-in media/CLI skips
    # are outside this gate, but every MySQL collection error/skip is recorded.
    path = report.nodeid.replace("\\", "/")
    mysql_path = path.startswith("tests/common/db/integration") or path.startswith((
        "tests/case/test_store_mysql.py", "tests/case/test_case_repository_contract.py"))
    if report.failed or (report.skipped and mysql_path):
        _collection_problems.append(report.nodeid)


_collection_problems = []


def pytest_sessionfinish(session, exitstatus):
    evidence = session.config._mysql_evidence
    evidence["collection_errors"] = list(_collection_problems)
    path = session.config.getoption("--mysql-report")
    if path:
        Path(path).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    if os.environ.get("DAESINGO_REQUIRE_MYSQL") == "1":
        reports = evidence["reports"]
        if any(r["outcome"] == "skipped" or r["xfail"] for r in reports):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(scope="session")
def mysql_server_url(request):
    if not os.environ.get("DAESINGO_MYSQL_URL"):
        if os.environ.get("DAESINGO_REQUIRE_MYSQL") == "1":
            pytest.fail("DAESINGO_MYSQL_URL required", pytrace=False)
        pytest.skip("DAESINGO_MYSQL_URL not set; real MySQL integration opt-in")
    _dependency_check()
    url = _test_url()
    if request.config._mysql_evidence["server_version"] is None:
        request.config._mysql_evidence["server_version"] = _preflight()
    return url


@pytest.fixture
def mysql_schema_url(mysql_server_url):
    engine = _control_engine(mysql_server_url)
    try:
        with _schema(engine) as name:
            yield mysql_server_url.set(database=name)
    finally:
        engine.dispose()


@pytest.fixture
def mysql_engine(mysql_schema_url):
    """Common application engine; Case's child conftest overrides this locally."""
    from daesingo.common.config import DbSettings
    from daesingo.common.db import create_worker_engine
    engine = create_worker_engine(DbSettings(url=mysql_schema_url.render_as_string(hide_password=False),
                                             pool_size=2, max_overflow=2))
    try:
        yield engine
    finally:
        engine.dispose()
