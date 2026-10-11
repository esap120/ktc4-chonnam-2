"""case 소유 migration env(잠정). 우선순위: 외부 connection → Alembic config URL → DAESINGO_MYSQL_URL. forward-only — downgrade를 운영 경로로 쓰지 않는다."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from daesingo.case.store_mysql import metadata

config = context.config
version_table = config.get_main_option("version_table") or "case_alembic_version"

if context.is_offline_mode():
    url = config.get_main_option("sqlalchemy.url") or os.environ["DAESINGO_MYSQL_URL"]
    context.configure(url=url, target_metadata=metadata, version_table=version_table, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    connectable = config.attributes.get("connection")
    if connectable is None:
        url = config.get_main_option("sqlalchemy.url") or os.environ["DAESINGO_MYSQL_URL"]
        connectable = create_engine(url)
    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata, version_table=version_table)
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(connection=connectable, target_metadata=metadata, version_table=version_table)
        with context.begin_transaction():
            context.run_migrations()
