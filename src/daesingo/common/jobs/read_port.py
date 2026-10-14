"""JSON-compatible JobExecution v1.1 projection for composition-root injection."""

from collections.abc import Iterable
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from daesingo.common.job_execution import JobExecution
from .schema import job_execution
from daesingo.common.usage.schema import usage_record

# Explicit allowlist: private columns cannot leak as the physical schema grows.
_FIELDS = ("execution_id", "job_id", "status", "attempt", "queued_at", "started_at",
           "ended_at", "produced", "failure_kind")


def read_executions(conn: Connection, job_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Read every attempt for the requested jobs; Case chooses representatives.

    Does not own commit/rollback/close or lock rows. Projects Final identities. UTC
    DATETIME(6) values get an explicit UTC offset at the Contract boundary.
    """
    ids = list(dict.fromkeys(job_ids))
    if not ids:
        return []
    statement = select(*(job_execution.c[name] for name in _FIELDS)).where(
        job_execution.c.job_id.in_(ids),
    ).order_by(job_execution.c.job_id, job_execution.c.attempt)
    rows = conn.execute(statement).mappings().all()
    refs = {}
    if rows:
        for execution, identity in conn.execute(select(
            usage_record.c.execution_ref, usage_record.c.usage_id
        ).where(usage_record.c.execution_ref.in_([r["execution_id"] for r in rows]))
          .order_by(usage_record.c.execution_ref, usage_record.c.usage_id)):
            refs.setdefault(execution, []).append(identity)
    executions = []
    for row in rows:
        payload = dict(row)
        for field in ("queued_at", "started_at", "ended_at"):
            if payload[field] is not None:
                payload[field] = payload[field].replace(tzinfo=timezone.utc)
        model = JobExecution(
            contract="JobExecution", contract_version="job-execution/v1.1",
            usage_refs=refs.get(payload["execution_id"], []), **payload,
        )
        executions.append(model.model_dump(mode="json"))
    return executions
