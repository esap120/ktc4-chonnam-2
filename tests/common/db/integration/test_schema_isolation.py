"""Real default-schema identity and no SQL for rejected target overrides."""

import re

import pytest
import sqlalchemy as sa

import mysql_harness as harness

pytestmark = pytest.mark.mysql


@pytest.mark.mysql_scenario("schema_identity")
@pytest.mark.mysql_check("harness", "schema_identity")
def test_default_schema_is_exactly_the_created_uuid_schema(mysql_schema_url, mysql_engine):
    assert re.fullmatch(r"rt02a_test_[0-9a-f]{32}", mysql_schema_url.database)
    with mysql_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT DATABASE()").scalar_one() == mysql_schema_url.database


@pytest.mark.mysql_scenario("schema_override_rejected")
@pytest.mark.parametrize("option", [pytest.param(option, marks=pytest.mark.mysql_check("harness", "schema_override_" + option))
                                  for option in ("database", "db", "init_command")])
def test_rejected_override_executes_no_sql_and_preserves_existing_schema(mysql_server_url, option):
    observer = harness._control_engine(mysql_server_url)
    try:
        with harness._schema(observer) as victim:
            with observer.connect() as conn:
                conn.exec_driver_sql(f"CREATE TABLE `{victim}`.sentinel (id INT PRIMARY KEY, value INT) ENGINE=InnoDB")
                conn.exec_driver_sql(f"INSERT INTO `{victim}`.sentinel VALUES (1, 17)")
                original_ddl = conn.exec_driver_sql(f"SHOW CREATE TABLE `{victim}`.sentinel").one()[1]
            value = f"USE `{victim}`" if option == "init_command" else victim
            malicious = mysql_server_url.update_query_dict({option: value})
            issued = []

            def record(conn, cursor, statement, parameters, context, executemany):
                issued.append(statement)

            sa.event.listen(sa.engine.Engine, "before_cursor_execute", record)
            fixture = harness.mysql_schema_url.__wrapped__(malicious)
            try:
                with pytest.raises(pytest.UsageError) as error:
                    next(fixture)
                assert str(error.value) == "MySQL test URL query options are not permitted"
            finally:
                fixture.close()
                sa.event.remove(sa.engine.Engine, "before_cursor_execute", record)
            assert issued == []  # no CREATE/DROP/USE/write, even transiently
            with observer.connect() as conn:
                assert conn.exec_driver_sql(f"SHOW CREATE TABLE `{victim}`.sentinel").one()[1] == original_ddl
                assert conn.exec_driver_sql(f"SELECT * FROM `{victim}`.sentinel").all() == [(1, 17)]
                assert conn.exec_driver_sql(f"SHOW TABLES FROM `{victim}`").all() == [("sentinel",)]
    finally:
        observer.dispose()
