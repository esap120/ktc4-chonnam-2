"""Worker-owned bridge to the existing Case 8-8 public surface.

Reader/timeline capabilities are supplied by composition (RT-10 owns durable
module results). Unsupported kinds preserve Case's fail-closed ValueError.
"""

from collections.abc import Callable

from sqlalchemy.engine import Connection

from daesingo.case.analysis_start import InitialSearchBudget
from daesingo.case.reflection import ExecutionOutcome, ProducedReader, reflect_execution
from daesingo.case.store import CaseStore
from daesingo.case.store_mysql import MySQLCaseRepository
from daesingo.case.timeline_source import CaseTimelineSource
from daesingo.common.jobs.read_port import read_executions
from daesingo.common.jobs.reflection import ReflectionInput, ReflectionResult, RuntimeJobRecord


def _store(conn: Connection) -> CaseStore:
    return CaseStore(repository=MySQLCaseRepository(), conn=conn, executions=read_executions)


class CaseReflector:
    def __init__(self, *, reader: ProducedReader, timelines: CaseTimelineSource,
                 store_factory: Callable[[Connection], CaseStore] = _store,
                 budget: InitialSearchBudget | None = None):
        self.reader, self.timelines, self.store_factory, self.budget = reader, timelines, store_factory, budget

    def reflect(self, conn: Connection, incoming: ReflectionInput) -> ReflectionResult:
        store = self.store_factory(conn)
        if store.conn is not conn:
            raise ValueError("reflection store must share caller connection")
        outcome = ExecutionOutcome(
            execution_id=incoming.execution_id, job_id=incoming.job_id, case_id=incoming.case_id,
            kind=incoming.kind, attempt=incoming.attempt, status=incoming.terminal.status,
            produced=tuple(ref.model_dump() for ref in incoming.terminal.produced),
            failure_kind=incoming.terminal.failure_kind,
        )
        result = reflect_execution(outcome, store=store, reader=self.reader,
            timelines=self.timelines, budget=self.budget)
        return ReflectionResult(result.status, result.reason, tuple(
            RuntimeJobRecord(job["job_id"], job["case_id"], job["kind"])
            for job in result.appended_job_records))
