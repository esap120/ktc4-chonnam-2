"""Reproduce the missing-failure-kind disclosure with a durable MySQL receipt."""

from pydantic import ValidationError
import pytest

from test_lifecycle_mysql import queue, repo, row, seed, listener  # noqa: F401
from test_validation_privacy import SECRET, PATH, assert_private_input_absent


pytestmark = pytest.mark.mysql


@pytest.mark.mysql_check("jobs", "finish_validation")
def test_finish_validation_error_hides_real_receipt_and_private_values(queue, repo, caplog):
    execution_id, = seed(queue)
    owner = SECRET + PATH
    repo.claim_one(queue, owner)
    with queue.begin() as conn:
        conn.exec_driver_sql("""UPDATE job_execution SET trace_id=%s,kind=%s,case_id=%s,
            cancel_requested_at=NOW(6),case_applied_at=NOW(6) WHERE execution_id=%s""",
                             (SECRET, PATH, SECRET + PATH, execution_id))
    before = row(queue, execution_id)
    token = before["claim_token"]
    boundaries = []
    with queue.connect() as conn:
        tx = conn.begin()
        try:
            with listener(conn, "commit", lambda c: boundaries.append("commit")), listener(
                    conn, "rollback", lambda c: boundaries.append("rollback")):
                with pytest.raises(ValidationError) as caught:
                    repo.finish(conn, execution_id, owner, status="FAILED")
                assert conn.in_transaction() and boundaries == []
                assert_private_input_absent(caught.value, [token, SECRET, PATH], caplog)
        finally:
            tx.rollback()
    assert row(queue, execution_id) == before
