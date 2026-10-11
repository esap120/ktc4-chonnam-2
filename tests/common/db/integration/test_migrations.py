"""RT-02(b) runner acceptance, including the RT-03(a) first Runtime revision."""

from contextlib import contextmanager
import importlib
import io
import os
import subprocess
import sys
import threading
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import event

from daesingo.common.db import create_migration_engine
from migration_support import ROOT, add_revision, copy_production, create_table, environment

pytestmark = pytest.mark.mysql


def runner():
    return importlib.import_module("daesingo.common.db.migrate")


def case_config():
    return Config(str(ROOT / "migrations/case/alembic.ini"))


def tables(conn):
    return {row[0] for row in conn.exec_driver_sql("SHOW TABLES")}


def expected_tables():
    return {"cases", "job_records", "correction_records", "analysis_scopes", "case_alembic_version", "runtime_alembic_version", "job_execution"}


@contextmanager
def observe(url):
    engine = create_migration_engine(url)
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


@pytest.mark.mysql_check("migration", "case_external_transaction")
def test_case_external_connection_skips_env_and_leaves_commit_to_caller(mysql_schema_url, monkeypatch):
    monkeypatch.delenv("DAESINGO_MYSQL_URL", raising=False)
    engine = create_migration_engine(mysql_schema_url)
    commits = []
    event.listen(engine, "commit", lambda conn: commits.append(True))
    try:
        with engine.begin() as conn:
            cfg = case_config()
            cfg.attributes["connection"] = conn
            cfg.set_main_option("sqlalchemy.url", "not-a-url")
            command.upgrade(cfg, "head")
            assert not conn.closed and conn.in_transaction()
            assert commits == []
            # DDL persists on MySQL, but the final version INSERT is caller-owned DML.
            with observe(mysql_schema_url) as observer:
                assert "cases" in tables(observer)
                assert observer.exec_driver_sql("SELECT COUNT(*) FROM case_alembic_version").scalar_one() == 0
        assert len(commits) == 1
        with observe(mysql_schema_url) as observer:
            assert observer.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"
    finally:
        engine.dispose()


@pytest.mark.mysql_check("migration", "case_url_precedence")
@pytest.mark.parametrize("source", ["environment", "config"])
def test_case_direct_url_paths_and_percent_encoding(mysql_schema_url, monkeypatch, source):
    cfg = case_config()
    url = mysql_schema_url.set(query={**mysql_schema_url.query, "program_name": "percent%value"}).render_as_string(hide_password=False)
    if source == "environment":
        monkeypatch.setenv("DAESINGO_MYSQL_URL", url)
    else:
        monkeypatch.setenv("DAESINGO_MYSQL_URL", "invalid-ambient-secret")
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == expected_tables() - {"runtime_alembic_version", "job_execution"}
        assert conn.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"


@pytest.mark.mysql_check("migration", "case_url_precedence")
def test_explicit_config_url_preserves_percent_encoded_password(mysql_schema_url, monkeypatch):
    name = "rt02b_" + uuid4().hex[:24]  # MySQL account names allow at most 32 chars.
    with observe(mysql_schema_url) as conn:
        conn.exec_driver_sql("CREATE USER %s@'%%' IDENTIFIED BY %s", (name, "percent%password"))
        conn.exec_driver_sql(f"GRANT ALL ON `{mysql_schema_url.database}`.* TO %s@'%%'", (name,))
    try:
        url = mysql_schema_url.set(username=name, password="percent%password").render_as_string(hide_password=False)
        cfg = case_config()
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        monkeypatch.setenv("DAESINGO_MYSQL_URL", "invalid-ambient-secret")
        command.upgrade(cfg, "head")
        with observe(mysql_schema_url) as conn:
            assert conn.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"
    finally:
        with observe(mysql_schema_url) as conn:
            conn.exec_driver_sql("DROP USER %s@'%%'", (name,))


@pytest.mark.mysql_check("migration", "case_offline_precedence")
@pytest.mark.parametrize("source", ["environment", "config"])
def test_case_offline_url_precedence_without_db_mutation(mysql_schema_url, monkeypatch, source):
    output = io.StringIO()
    cfg = Config(str(ROOT / "migrations/case/alembic.ini"), output_buffer=output)
    if source == "config":
        monkeypatch.setenv("DAESINGO_MYSQL_URL", "invalid-ambient-secret")
        cfg.set_main_option("sqlalchemy.url", mysql_schema_url.render_as_string(hide_password=False).replace("%", "%%"))
    else:
        monkeypatch.setenv("DAESINGO_MYSQL_URL", mysql_schema_url.render_as_string(hide_password=False))
    command.upgrade(cfg, "head", sql=True)
    assert "CREATE TABLE cases" in output.getvalue()
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == set()


@pytest.mark.mysql_check("migration", "empty_schema")
@pytest.mark.mysql_check("migration", "idempotency")
def test_production_runner_empty_schema_and_second_run_preserve_data(mysql_schema_url, monkeypatch):
    m = runner()
    monkeypatch.delenv("DAESINGO_MYSQL_URL", raising=False)
    result = m.upgrade_all(mysql_schema_url)
    assert result.completed == ("case", "runtime")
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == expected_tables()
        assert conn.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"
        assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0002"
        conn.exec_driver_sql("INSERT INTO cases VALUES ('retained', 0, 'INIT', 0, '{}', NOW(6), NOW(6))")
        conn.commit()
        schema = {name: conn.exec_driver_sql(f"SHOW CREATE TABLE `{name}`").one()[1] for name in expected_tables()}
        data = conn.exec_driver_sql("SELECT * FROM cases").all()
    assert m.upgrade_all(mysql_schema_url).completed == ("case", "runtime")
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == expected_tables()
        assert conn.exec_driver_sql("SELECT case_id FROM cases").scalar_one() == "retained"
        assert conn.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"
        assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "runtime_0002"
        assert {name: conn.exec_driver_sql(f"SHOW CREATE TABLE `{name}`").one()[1] for name in expected_tables()} == schema
        assert conn.exec_driver_sql("SELECT * FROM cases").all() == data


@pytest.mark.mysql_check("migration", "explicit_target")
def test_runner_ignores_wrong_ambient_schema(mysql_schema_url, mysql_server_url, monkeypatch):
    with observe(mysql_server_url) as conn:
        before = tables(conn)
    monkeypatch.setenv("DAESINGO_MYSQL_URL", mysql_server_url.render_as_string(hide_password=False))
    runner().upgrade_all(mysql_schema_url)
    with observe(mysql_server_url) as conn:
        assert tables(conn) == before
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == expected_tables()


@pytest.mark.mysql_check("migration", "first_runtime_revision")
def test_same_runner_applies_future_first_runtime_revision(mysql_schema_url, tmp_path):
    root = copy_production(tmp_path / "migrations")
    m = runner()
    m.upgrade_all(mysql_schema_url, migrations_root=root)
    # Extend the real first revision rather than introduce a second graph head.
    add_revision(root / "runtime", "test_runtime_first", "runtime_0002", create_table("test_future_runtime"))
    m.upgrade_all(mysql_schema_url, migrations_root=root)
    with observe(mysql_schema_url) as conn:
        assert "test_future_runtime" in tables(conn)
        assert conn.exec_driver_sql("SELECT version_num FROM runtime_alembic_version").scalar_one() == "test_runtime_first"


@pytest.mark.mysql_check("migration", "partial_failure")
def test_real_sql_failure_keeps_prior_module_and_partial_ddl_stops_following(mysql_schema_url, tmp_path, monkeypatch):
    m = runner()
    environment(tmp_path, "first", [("first1", None, create_table("test_first"))])
    environment(tmp_path, "middle", [("middle1", None, create_table("test_partial") + "\n" + create_table("test_partial"))])
    environment(tmp_path, "last", [("last1", None, create_table("test_never"))])
    monkeypatch.setattr(m, "REGISTRY", tuple(m.ModuleMigration(n, n, n + "_alembic_version") for n in ("first", "middle", "last")))
    for _ in range(2):
        with pytest.raises(m.MigrationFailure) as error:
            m.upgrade_all(mysql_schema_url, migrations_root=tmp_path)
        assert error.value.completed == ("first",)
        assert error.value.module == "middle"
        with observe(mysql_schema_url) as conn:
            assert tables(conn) == {"test_first", "first_alembic_version", "test_partial", "middle_alembic_version"}
            assert conn.exec_driver_sql("SELECT version_num FROM first_alembic_version").scalar_one() == "first1"
            assert conn.exec_driver_sql("SELECT COUNT(*) FROM middle_alembic_version").scalar_one() == 0


@pytest.mark.mysql_check("migration", "revision_preflight")
@pytest.mark.parametrize("broken", ["unknown", "rows", "heads"])
def test_revision_errors_are_detected_before_any_module_ddl(mysql_schema_url, tmp_path, monkeypatch, broken):
    m = runner()
    environment(tmp_path, "first", [("first1", None, create_table("test_never_first"))])
    environment(tmp_path, "last", [("last1", None, create_table("test_never_last"))])
    monkeypatch.setattr(m, "REGISTRY", tuple(m.ModuleMigration(n, n, n + "_alembic_version") for n in ("first", "last")))
    if broken == "heads":
        add_revision(tmp_path / "last", "otherhead", None, "pass")
    else:
        with observe(mysql_schema_url) as conn:
            conn.exec_driver_sql("CREATE TABLE last_alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO last_alembic_version VALUES ('unknown-secret')")
            if broken == "rows":
                conn.exec_driver_sql("INSERT INTO last_alembic_version VALUES ('last1')")
            conn.commit()
    with pytest.raises(m.MigrationFailure) as error:
        m.upgrade_all(mysql_schema_url, migrations_root=tmp_path)
    assert error.value.completed == ()
    assert error.value.code == {"unknown": "unknown_revision", "rows": "multiple_database_heads", "heads": "multiple_script_heads"}[broken]
    assert "unknown-secret" not in str(error.value)
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == (set() if broken == "heads" else {"last_alembic_version"})


@pytest.mark.mysql_check("migration", "process_guard")
def test_nested_and_concurrent_calls_are_rejected_and_state_restored(mysql_schema_url, monkeypatch):
    m = runner()
    original = m.create_migration_engine
    errors = []
    engines = []
    connections = []

    def attempt():
        try:
            m.upgrade_all(mysql_schema_url)
        except m.MigrationFailure as error:
            errors.append(error.code)

    def factory(url, **kwargs):
        attempt()
        thread = threading.Thread(target=attempt)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
        engine = original(url, **kwargs)
        engines.append(engine)
        event.listen(engine, "begin", lambda conn: connections.append(conn))
        return engine

    monkeypatch.setattr(m, "create_migration_engine", factory)
    m.upgrade_all(mysql_schema_url)
    assert errors == ["runner_busy", "runner_busy"]
    assert len(engines) == 1
    assert len({id(conn) for conn in connections}) >= 3  # preflight + two independent modules
    assert all(conn.closed for conn in connections)
    monkeypatch.setattr(m, "create_migration_engine", original)
    m.upgrade_all(mysql_schema_url)
    with pytest.raises(m.MigrationFailure):
        m.upgrade_all("invalid-private-url")
    m.upgrade_all(mysql_schema_url)
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(m, "create_migration_engine", interrupt)
    with pytest.raises(KeyboardInterrupt):
        m.upgrade_all(mysql_schema_url)
    monkeypatch.setattr(m, "create_migration_engine", original)
    m.upgrade_all(mysql_schema_url)


@pytest.mark.mysql_check("migration", "cli_stdin")
def test_real_cli_stdin_success_and_observer_versions(mysql_schema_url):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
    env.pop("DAESINGO_MYSQL_URL", None)
    result = subprocess.run([sys.executable, "-B", "-m", "daesingo.common.db.migrate", "--database-url-stdin"],
                            input=mysql_schema_url.render_as_string(hide_password=False) + "\n",
                            env=env, cwd=ROOT.parent, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "migration: complete case runtime\n"
    with observe(mysql_schema_url) as conn:
        assert tables(conn) == expected_tables()
        assert conn.exec_driver_sql("SELECT version_num FROM case_alembic_version").scalar_one() == "case_0001"


@pytest.mark.mysql_check("migration", "process_guard")
def test_module_entrypoint_and_import_share_process_guard(mysql_schema_url):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
    # Run the real module entrypoint. A factory callback imports the canonical
    # API, exactly as an in-process consumer could while __main__ is running.
    bootstrap = '''
import runpy
from daesingo.common.db import engines
original = engines.create_migration_engine
outcomes = []
def factory(url, **kwargs):
    if not outcomes:
        outcomes.append("attempting")
        from daesingo.common.db.migrate import upgrade_all, MigrationFailure
        try:
            upgrade_all(url)
        except MigrationFailure as error:
            outcomes[:] = [error.code]
        else:
            outcomes[:] = ["nested_call_succeeded"]
    return original(url, **kwargs)
engines.create_migration_engine = factory
try:
    runpy.run_module("daesingo.common.db.migrate", run_name="__main__")
except SystemExit as error:
    assert error.code == 0
assert outcomes == ["runner_busy"], outcomes
'''
    result = subprocess.run([sys.executable, "-B", "-c", bootstrap, "--database-url-stdin"],
                            input=mysql_schema_url.render_as_string(hide_password=False),
                            env=env, cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
