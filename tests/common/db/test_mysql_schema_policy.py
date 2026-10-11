"""Unsafe connection options must fail before engine creation or any SQL."""

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
import os
from pathlib import Path
import subprocess
import sys

import mysql_harness as harness


UNSAFE_OPTIONS = (
    "database", "db", "host", "port", "unix_socket", "user", "username",
    "password", "passwd", "init_command", "read_default_file", "read_default_group",
    "sql_mode", "client_flag", "autocommit", "defer_connect", "cursorclass", "conv",
    "auth_plugin_map", "unknown_future_option",
)
MESSAGE = "MySQL test URL query options are not permitted"


@pytest.mark.parametrize("option", UNSAFE_OPTIONS)
def test_unsafe_query_is_rejected_by_url_validation_without_disclosing_values(monkeypatch, option):
    url = make_url("mysql+pymysql://private-user:private-password@127.0.0.1/private_test_schema")
    url = url.update_query_dict({option: "private-value-C:/private/path"})
    monkeypatch.setenv("DAESINGO_MYSQL_URL", url.render_as_string(hide_password=False))
    with pytest.raises(pytest.UsageError) as error:
        harness._test_url()
    assert str(error.value) == MESSAGE


@pytest.mark.parametrize("option", UNSAFE_OPTIONS)
def test_direct_control_engine_rejects_query_before_creating_engine(monkeypatch, option):
    url = make_url("mysql+pymysql://private-user:private-password@127.0.0.1/private_test_schema")
    url = url.update_query_dict({option: "private-value"})
    created = []
    monkeypatch.setattr(sa, "create_engine", lambda *args, **kwargs: created.append(1))
    with pytest.raises(pytest.UsageError) as error:
        harness._control_engine(url)
    assert str(error.value) == MESSAGE
    assert created == []


def test_schema_context_rejects_unvalidated_engine_before_ddl():
    # Engine construction alone is lazy. No network connection is attempted.
    engine = sa.create_engine("mysql+pymysql://private-user:private-password@127.0.0.1:1/private_test_schema?database=private-victim")
    try:
        with pytest.raises(pytest.UsageError) as error:
            with harness._schema(engine):
                pytest.fail("unsafe schema context must not run")
        assert str(error.value) == MESSAGE
    finally:
        engine.dispose()


@pytest.mark.parametrize("require", ["0", "1"])
def test_unsafe_url_is_rejected_before_unchanged_case_fixture_can_create_engine(require):
    env = dict(os.environ, DAESINGO_REQUIRE_MYSQL=require, PYTHONDONTWRITEBYTECODE="1",
               DAESINGO_MYSQL_URL="mysql+pymysql://private-user:private-password@127.0.0.1:1/private_test_schema?database=private-victim")
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                             "tests/case/test_store_mysql.py", "--collect-only", "-q", "-p", "no:cacheprovider"],
                            cwd=Path(__file__).resolve().parents[3], env=env, text=True,
                            encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode != 0
    assert MESSAGE in result.stdout + result.stderr
    assert "private-" not in result.stdout + result.stderr
