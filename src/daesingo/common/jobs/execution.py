"""Execution-scoped invocation data, without DB resources or domain state."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from daesingo.common.job_execution import RuntimeContractRef
from daesingo.common.jobs.heartbeat import OwnershipFence
from daesingo.common.jobs.cancel import CancelSignal
from daesingo.common.usage.port import UsageSink


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    execution_id: str
    job_id: str
    case_id: str
    kind: str
    attempt: int
    trace_id: str
    cancel_signal: CancelSignal = field(default_factory=CancelSignal, compare=False, repr=False)
    usage_sink: UsageSink | None = field(default=None, compare=False, repr=False)
    ownership: OwnershipFence = field(default_factory=OwnershipFence, compare=False, repr=False)

    def checkpoint(self) -> None:
        self.cancel_signal.checkpoint()


class HandlerResult(BaseModel):
    """T1 facts only; Runtime never maps a module's failure taxonomy."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["SUCCEEDED", "FAILED"] = "SUCCEEDED"
    produced: tuple[RuntimeContractRef, ...] = ()
    failure_kind: str | None = Field(default=None, min_length=1, max_length=191)

    @model_validator(mode="after")
    def terminal_shape(self):
        if (self.status == "FAILED") != (self.failure_kind is not None):
            raise ValueError("inconsistent handler terminal result")
        if len({(r.kind, r.ref) for r in self.produced}) != len(self.produced):
            raise ValueError("duplicate produced reference")
        return self


def runtime_failure(kind: str) -> HandlerResult:
    return HandlerResult(status="FAILED", failure_kind=kind)


def validated_terminal(value: HandlerResult) -> HandlerResult:
    """Snapshot terminal facts safely, including model_copy/object tampering.

    Serialization can warn with raw values, or silently omit extra stored
    fields. Check the stored shape first and contain serializer errors.
    Contract reference parsing elsewhere keeps its existing extra policy.
    """
    try:
        if (type(value) is not HandlerResult or set(value.__dict__) != set(HandlerResult.model_fields)
                or value.__pydantic_extra__ or type(value.produced) is not tuple):
            raise ValueError()
        for ref in value.produced:
            if (type(ref) is not RuntimeContractRef or set(ref.__dict__) != set(RuntimeContractRef.model_fields)
                    or ref.__pydantic_extra__):
                raise ValueError()
        return HandlerResult.model_validate(value.model_dump(warnings="error"))
    except Exception:
        raise ValueError("invalid handler terminal result") from None
