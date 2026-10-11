"""Runtime-owned revisions on a caller-owned transaction Connection.

Online commands require a caller-owned transaction Connection. No env/config
secret loading, engine creation or independent commit/close happens here.
"""

from alembic import context

config = context.config
connection = config.attributes["connection"]
if not connection.in_transaction():
    raise RuntimeError("Runtime migrations require a caller-owned transaction")
context.configure(connection=connection, target_metadata=None,
                  version_table=config.get_main_option("version_table"))
with context.begin_transaction():
    context.run_migrations()
