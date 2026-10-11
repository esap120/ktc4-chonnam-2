"""Explicit, forward-only Alembic runner; never called at application startup.

Run once before starting services. Concurrent processes are NOT serialized here.
MySQL implicit-commit DDL cannot be rolled back as a module or runner transaction.
The CLI receives a URL through explicit stdin transport, never argv/env/files.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import sys
import warnings
from threading import Lock

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL, make_url

from .engines import create_migration_engine


@dataclass(frozen=True)
class ModuleMigration:
    module: str
    directory: str
    version_table: str


REGISTRY = (
    ModuleMigration("case", "case", "case_alembic_version"),
    ModuleMigration("runtime", "runtime", "runtime_alembic_version"),
)
# ``python -m`` loads this file as __main__; later canonical imports must use
# the SAME lock. The parent package is shared by both module identities.
_running = vars(sys.modules[__package__]).setdefault("_migration_runner_lock", Lock())
_identifier = re.compile(r"[a-z][a-z0-9_]*\Z")
_default_root = Path(__file__).resolve().parents[4] / "migrations"


@dataclass(frozen=True)
class MigrationReport:
    completed: tuple[str, ...]


class MigrationFailure(RuntimeError):
    """Only trusted codes/registry identifiers; never render underlying exceptions."""

    def __init__(self, code: str, *, module: str | None = None, completed: tuple[str, ...] = ()):
        self.code = code
        self.module = module
        self.completed = completed
        super().__init__(f"migration: {code}")


@dataclass(frozen=True)
class _Environment:
    entry: ModuleMigration
    config: Config
    script: ScriptDirectory
    revisions: frozenset[str]


def validate_environments(migrations_root: Path | None = None) -> tuple[_Environment, ...]:
    """Validate the entire declared inventory and graph before any DB work.

Discovery checks completeness only: execution always follows REGISTRY.
Migration source is trusted executable release code, not a plugin sandbox.
"""
    try:
        root = Path(migrations_root if migrations_root is not None else _default_root).resolve()
        names, paths, tables = set(), set(), set()
        for entry in REGISTRY:
            directory = (root / entry.directory).resolve()
            if (not _identifier.fullmatch(entry.module) or not _identifier.fullmatch(entry.version_table)
                    or entry.module in names or directory in paths or entry.version_table in tables
                    or directory.parent != root):
                raise MigrationFailure("invalid_registry")
            names.add(entry.module)
            paths.add(directory)
            tables.add(entry.version_table)
        if not names:
            raise MigrationFailure("invalid_registry")
        discovered = {child.resolve() for child in root.iterdir() if child.is_dir() and (child / "env.py").is_file()}
        if discovered != paths:
            raise MigrationFailure("invalid_environment")
        result = []
        for entry in REGISTRY:
            directory = root / entry.directory
            if not (directory / "alembic.ini").is_file() or not (directory / "versions").is_dir():
                raise MigrationFailure("invalid_environment", module=entry.module)
            config = Config(str(directory / "alembic.ini"))
            if config.get_main_option("version_table") != entry.version_table:
                raise MigrationFailure("invalid_environment", module=entry.module)
            # Alembic warns on malformed graphs (e.g. duplicate revision IDs).
            # Default warning formatting reveals paths; reject instead of emit.
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                script = ScriptDirectory.from_config(config)
                if Path(script.dir).resolve() != directory.resolve():
                    raise MigrationFailure("invalid_environment", module=entry.module)
                if len(script.get_heads()) > 1:
                    raise MigrationFailure("multiple_script_heads", module=entry.module)
                revisions = frozenset(revision.revision for revision in script.walk_revisions())
            result.append(_Environment(entry, config, script, revisions))
        return tuple(result)
    except MigrationFailure:
        raise
    except Exception:
        raise MigrationFailure("invalid_environment") from None


def _validated_url(value: str | URL) -> URL:
    url = make_url(value)
    if url.drivername != "mysql+pymysql" or not url.host or not url.username or not url.database:
        raise ValueError("invalid URL")
    return url


def upgrade_all(
    url: str | URL, *, migrations_root: Path | None = None,
    connect_timeout: float | None = None, read_timeout: float | None = None,
    write_timeout: float | None = None,
) -> MigrationReport:
    """Upgrade every registered env to head, stopping at the first failure.

Own one NullPool engine, a read-only preflight connection, then a new transaction
connection per module. No retry/stamp/downgrade/resume or secret-source lookup.
Omitted timeouts retain driver defaults; application B-D7 limits do not apply.
Successful modules remain applied after a later failure. Partial failed-revision
DDL may remain too: inspection/repair is required before retrying that revision.
"""
    if not _running.acquire(blocking=False):
        raise MigrationFailure("runner_busy")
    engine = None
    completed: list[str] = []
    current = None
    try:
        environments = validate_environments(migrations_root)
        engine = create_migration_engine(_validated_url(url), connect_timeout=connect_timeout,
                                         read_timeout=read_timeout, write_timeout=write_timeout)
        # Finish ALL read-only preflight before starting any module DDL. Close the
        # autobegun read transaction before Alembic receives a fresh transaction.
        with engine.connect() as conn:
            for env in environments:
                current = env.entry.module
                context = MigrationContext.configure(conn, opts={"version_table": env.entry.version_table})
                heads = context.get_current_heads()
                if len(heads) > 1:
                    raise MigrationFailure("multiple_database_heads", module=current)
                if any(head not in env.revisions for head in heads):
                    raise MigrationFailure("unknown_revision", module=current)
        for env in environments:
            current = env.entry.module
            # This owns commit of the version DML, NOT atomic rollback of DDL.
            with engine.begin() as conn:
                env.config.attributes["connection"] = conn
                try:
                    command.upgrade(env.config, "head")
                finally:
                    env.config.attributes.pop("connection", None)
            completed.append(current)
        return MigrationReport(tuple(completed))
    except MigrationFailure:
        raise
    except Exception:
        raise MigrationFailure("execution_failed", module=current, completed=tuple(completed)) from None
    finally:
        try:
            if engine is not None:
                engine.dispose()
        finally:
            _running.release()


def main(argv: list[str] | None = None) -> int:
    """Safe CLI output deliberately excludes argparse's raw argument echo."""
    try:
        args = sys.argv[1:] if argv is None else argv
        if args != ["--database-url-stdin"]:
            print("migration: invalid_arguments", file=sys.stderr)
            return 2
        try:
            if sys.stdin.isatty():
                raise ValueError("stdin must be a non-echoing transport")
            value = sys.stdin.read(65537).strip()
            if not value or len(value) > 65536 or any(char in value for char in "\r\n\x00"):
                raise ValueError("one URL required")
            url = _validated_url(value)
        except Exception:
            print("migration: invalid_input", file=sys.stderr)
            return 2
        report = upgrade_all(url)
        print("migration: complete " + " ".join(report.completed))
        return 0
    except KeyboardInterrupt:
        print("migration: interrupted", file=sys.stderr)
        return 130
    except Exception:
        print("migration: execution_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
