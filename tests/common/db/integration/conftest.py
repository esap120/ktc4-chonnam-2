"""Only test tables; no Runtime schema or migration runner."""

from contextlib import ExitStack

import pytest

from daesingo.common.config import DbSettings


@pytest.fixture
def db_settings(mysql_schema_url):
    return DbSettings(url=mysql_schema_url.render_as_string(hide_password=False))


@pytest.fixture
def engines():
    with ExitStack() as stack:
        def own(engine):
            stack.callback(engine.dispose)
            return engine
        yield own


@pytest.fixture
def probe(mysql_engine):
    with mysql_engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE tx_counter (id INT PRIMARY KEY, value INT NOT NULL) ENGINE=InnoDB")
        conn.exec_driver_sql("CREATE TABLE tx_effect (operation_id VARCHAR(64) PRIMARY KEY, attempt_no INT NOT NULL) ENGINE=InnoDB")
        conn.exec_driver_sql("INSERT INTO tx_counter VALUES (1, 0), (2, 0)")
    return mysql_engine
