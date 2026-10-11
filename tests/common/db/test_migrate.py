"""Runner input/graph/CLI contracts; MySQL behavior is tested separately."""

from dataclasses import FrozenInstanceError
import importlib
import io
import os
import subprocess
import sys
import warnings

import pytest

from migration_support import ROOT, environment


def runner():
    return importlib.import_module("daesingo.common.db.migrate")


@pytest.mark.parametrize("broken", ["module", "path", "version", "missing", "unregistered", "ini", "heads"])
def test_invalid_registry_or_graph_fails_before_engine_creation(tmp_path, monkeypatch, broken):
    m = runner()
    environment(tmp_path, "first")
    environment(tmp_path, "second")
    first = m.ModuleMigration("first", "first", "first_alembic_version")
    second = m.ModuleMigration("second", "second", "second_alembic_version")
    if broken == "module":
        second = m.ModuleMigration("first", "second", "second_alembic_version")
    elif broken == "path":
        second = m.ModuleMigration("second", "first", "second_alembic_version")
    elif broken == "version":
        second = m.ModuleMigration("second", "second", "first_alembic_version")
    elif broken == "missing":
        second = m.ModuleMigration("second", "absent", "second_alembic_version")
    elif broken == "unregistered":
        environment(tmp_path, "unregistered")
    elif broken == "ini":
        (tmp_path / "second/alembic.ini").write_text("[alembic]\nversion_table=wrong\n", encoding="ascii")
    elif broken == "heads":
        environment(tmp_path, "second", [("a", None, "pass"), ("b", None, "pass")])
    monkeypatch.setattr(m, "REGISTRY", (first, second))

    def forbidden(*args, **kwargs):
        pytest.fail("invalid deployment must be rejected before creating an engine")

    monkeypatch.setattr(m, "create_migration_engine", forbidden)
    with pytest.raises(m.MigrationFailure) as error:
        m.upgrade_all("mysql+pymysql://private:secret@private-host/test_db", migrations_root=tmp_path)
    assert error.value.code in {"invalid_registry", "invalid_environment", "multiple_script_heads"}
    assert "private" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_production_inventory_is_complete_and_immutable():
    m = runner()
    m.validate_environments(ROOT / "migrations")
    assert isinstance(m.REGISTRY, tuple)
    with pytest.raises(FrozenInstanceError):
        m.REGISTRY[0].module = "changed"


@pytest.mark.parametrize("argv", [[], ["--database-url", "secret-argument"], ["downgrade"], ["--database-url-stdin", "secret-path"], ["--help", "secret-path"]])
def test_cli_usage_errors_never_echo_arguments(argv, capsys):
    assert runner().main(argv) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "migration: invalid_arguments\n"


@pytest.mark.parametrize("value", ["", "not-a-url-private-path", "mysql+pymysql://private:secret@private-host/", "mysql+pymysql://private:secret@private-host/test_db\nextra-secret"])
def test_cli_bad_stdin_is_usage_error_and_sanitized(value, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(value))
    assert runner().main(["--database-url-stdin"]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "migration: invalid_input\n"


@pytest.mark.parametrize("failure,expected", [(RuntimeError("secret-path secret-exception"), 1), (KeyboardInterrupt(), 130)])
def test_cli_execution_error_and_interrupt_are_sanitized(failure, expected, monkeypatch, capsys):
    m = runner()
    monkeypatch.setattr(sys, "stdin", io.StringIO("mysql+pymysql://private:secret@private-host/test_db\n"))

    def fail(url):
        raise failure

    monkeypatch.setattr(m, "upgrade_all", fail)
    assert m.main(["--database-url-stdin"]) == expected
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err in {"migration: execution_failed\n", "migration: interrupted\n"}


def test_module_cli_connection_failure_does_not_leak_credentials_or_paths():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-B", "-m", "daesingo.common.db.migrate", "--database-url-stdin"],
        input="mysql+pymysql://private-user:private-password@127.0.0.1:1/private_schema?program_name=private-query\n",
        env=env, cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "migration: execution_failed\n"


def test_duplicate_revision_warning_cannot_expose_source_paths(tmp_path, monkeypatch, capsys):
    m = runner()
    directory = environment(tmp_path, "case", [("duplicate", None, "pass")])
    (directory / "versions/copy.py").write_text((directory / "versions/duplicate.py").read_text(encoding="utf-8"), encoding="utf-8")
    environment(tmp_path, "runtime")
    monkeypatch.setattr(m, "_default_root", tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("mysql+pymysql://private:secret@127.0.0.1:1/test_db"))
    with warnings.catch_warnings(record=True) as emitted:
        warnings.simplefilter("always")
        assert m.main(["--database-url-stdin"]) == 1
    assert not emitted  # Python's default warning formatter includes source paths.
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "migration: execution_failed\n"
