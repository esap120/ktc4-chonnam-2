"""JobExecution v1.1 모델과 in-memory lifecycle 구현."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


JobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "STALE", "CANCELLED"]
TerminalStatus = Literal["SUCCEEDED", "FAILED", "STALE", "CANCELLED"]


class RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class RuntimeContractRef(RuntimeModel):
    kind: str = Field(min_length=1)
    ref: str = Field(min_length=1)


class JobExecution(RuntimeModel):
    contract: Literal["JobExecution"]
    contract_version: Literal["job-execution/v1.1"]
    execution_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    status: JobStatus
    attempt: int = Field(ge=1)
    queued_at: AwareDatetime
    started_at: AwareDatetime | None
    ended_at: AwareDatetime | None
    produced: list[RuntimeContractRef]
    failure_kind: str | None
    usage_refs: list[str]

    @model_validator(mode="after")
    def state_fields_are_consistent(self) -> JobExecution:
        if self.status == "QUEUED" and (self.started_at is not None or self.ended_at is not None):
            raise ValueError("QUEUED는 started_at과 ended_at이 null이어야 합니다")
        if self.status == "RUNNING" and (self.started_at is None or self.ended_at is not None):
            raise ValueError("RUNNING은 started_at이 있고 ended_at이 null이어야 합니다")
        if self.status in {"SUCCEEDED", "FAILED", "CANCELLED"} and self.ended_at is None:
            raise ValueError("종료 상태에는 ended_at이 필요합니다")
        if self.status == "SUCCEEDED" and self.started_at is None:
            raise ValueError("SUCCEEDED에는 started_at이 필요합니다")
        if self.status == "FAILED" and self.failure_kind is None:
            raise ValueError("FAILED에는 failure_kind가 필요합니다")
        if self.status in {"QUEUED", "RUNNING", "SUCCEEDED", "CANCELLED"} and (
            self.failure_kind is not None
        ):
            raise ValueError("실패 상태가 아닌 실행의 failure_kind는 null이어야 합니다")
        if self.started_at is not None and self.started_at < self.queued_at:
            raise ValueError("started_at은 queued_at보다 빠를 수 없습니다")
        if self.ended_at is not None:
            lower_bound = self.started_at or self.queued_at
            if self.ended_at < lower_bound:
                raise ValueError("ended_at은 실행의 앞선 시각보다 빠를 수 없습니다")
        if len(set(self.usage_refs)) != len(self.usage_refs):
            raise ValueError("usage_refs는 중복될 수 없습니다")
        produced_keys = {(item.kind, item.ref) for item in self.produced}
        if len(produced_keys) != len(self.produced):
            raise ValueError("produced ref는 중복될 수 없습니다")
        return self


class JobExecutionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    """Validate against the single existing lifecycle table, without mutation."""
    if target not in InMemoryJobExecutionStore._TRANSITIONS.get(current, set()):
        raise JobExecutionError(
            "INVALID_STATUS_TRANSITION", f"{current}에서 {target}(으)로 전이할 수 없습니다",
        )


class InMemoryJobExecutionStore:
    """Job별 attempt와 허용 상태 전이를 보존하는 실행 저장소."""

    _TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
        "QUEUED": {"RUNNING", "FAILED", "CANCELLED"},
        "RUNNING": {"SUCCEEDED", "FAILED", "STALE", "CANCELLED"},
        "SUCCEEDED": set(),
        "FAILED": set(),
        "STALE": set(),
        "CANCELLED": set(),
    }

    def __init__(self) -> None:
        self._executions: dict[str, JobExecution] = {}
        self._by_job: dict[str, list[str]] = {}

    @classmethod
    def from_executions(cls, executions: Iterable[JobExecution]) -> InMemoryJobExecutionStore:
        store = cls()
        for execution in executions:
            store.add_snapshot(execution)
        return store

    def add_snapshot(self, execution: JobExecution) -> None:
        if execution.execution_id in self._executions:
            raise ValueError("execution_id는 재사용할 수 없습니다")
        attempts = self._by_job.setdefault(execution.job_id, [])
        expected_attempt = len(attempts) + 1
        if execution.attempt != expected_attempt:
            raise ValueError("attempt는 같은 job_id 안에서 1부터 연속 증가해야 합니다")
        self._executions[execution.execution_id] = execution
        attempts.append(execution.execution_id)

    def queue_execution(
        self,
        job_id: str,
        queued_at: datetime,
        *,
        execution_id: str | None = None,
    ) -> JobExecution:
        if not job_id:
            raise ValueError("job_id는 비어 있을 수 없습니다")
        attempt = len(self._by_job.get(job_id, [])) + 1
        execution = JobExecution(
            contract="JobExecution",
            contract_version="job-execution/v1.1",
            execution_id=execution_id or f"exec_{uuid4().hex}",
            job_id=job_id,
            status="QUEUED",
            attempt=attempt,
            queued_at=queued_at,
            started_at=None,
            ended_at=None,
            produced=[],
            failure_kind=None,
            usage_refs=[],
        )
        self.add_snapshot(execution)
        return execution

    def start_execution(self, execution_id: str, started_at: datetime) -> JobExecution:
        return self._transition(execution_id, "RUNNING", started_at=started_at)

    def finish_execution(
        self,
        execution_id: str,
        status: TerminalStatus,
        ended_at: datetime | None,
        *,
        produced: Iterable[RuntimeContractRef | dict[str, Any]] = (),
        failure_kind: str | None = None,
        usage_refs: Iterable[str] = (),
    ) -> JobExecution:
        parsed_produced = [RuntimeContractRef.model_validate(item) for item in produced]
        return self._transition(
            execution_id,
            status,
            ended_at=ended_at,
            produced=parsed_produced,
            failure_kind=failure_kind,
            usage_refs=list(usage_refs),
        )

    def get(self, execution_id: str) -> JobExecution:
        try:
            return self._executions[execution_id]
        except KeyError as error:
            raise JobExecutionError("UNKNOWN_EXECUTION", "등록되지 않은 execution_id입니다") from error

    def list_for_job(self, job_id: str) -> list[JobExecution]:
        return [self._executions[item] for item in self._by_job.get(job_id, [])]

    def _transition(self, execution_id: str, status: JobStatus, **changes: Any) -> JobExecution:
        current = self.get(execution_id)
        validate_transition(current.status, status)
        updated = current.model_copy(update={"status": status, **changes})
        validated = JobExecution.model_validate(updated.model_dump())
        self._executions[execution_id] = validated
        return validated
