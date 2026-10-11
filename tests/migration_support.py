"""Temporary Alembic environments for runner acceptance, never production DDL."""

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def copy_production(target):
    shutil.copytree(ROOT / "migrations", target)
    return target


def environment(root, name, revisions=()):
    directory = root / name
    (directory / "versions").mkdir(parents=True, exist_ok=True)
    (directory / "alembic.ini").write_text(
        f"[alembic]\nscript_location = %(here)s\nversion_table = {name}_alembic_version\n",
        encoding="ascii",
    )
    (directory / "env.py").write_text(
        "from alembic import context\n"
        "config = context.config\n"
        "connection = config.attributes['connection']\n"
        "assert connection.in_transaction()\n"
        "context.configure(connection=connection, version_table=config.get_main_option('version_table'))\n"
        "with context.begin_transaction():\n    context.run_migrations()\n",
        encoding="utf-8",
    )
    for revision, parent, body in revisions:
        add_revision(directory, revision, parent, body)
    return directory


def add_revision(directory, revision, parent, body):
    (directory / "versions" / f"{revision}.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        f"revision = {revision!r}\ndown_revision = {parent!r}\n"
        "branch_labels = None\ndepends_on = None\n"
        "def upgrade():\n" + "\n".join("    " + line for line in body.splitlines()) +
        "\ndef downgrade():\n    raise NotImplementedError('forward-only')\n",
        encoding="utf-8",
    )


def create_table(name):
    return f"op.create_table({name!r}, sa.Column('id', sa.Integer, primary_key=True))"
