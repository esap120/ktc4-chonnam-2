"""Runtime-owned invocation port; no persistence or provider dependencies."""

from collections.abc import Mapping
from typing import Any, Protocol


class UsageError(RuntimeError):
    """Sanitized failure outside provider retry taxonomy."""
    code = "STATE"

    def __init__(self):
        super().__init__("Runtime usage " + self.code.lower() + " failure")


class UsageValidationError(UsageError):
    code = "VALIDATION"


class UsageConflictError(UsageError):
    code = "CONFLICT"


class UsageStateError(UsageError):
    code = "STATE"


class UsagePersistenceError(UsageError):
    code = "PERSISTENCE"

    def __init__(self, *, usage_id: str | None = None):
        # A failed begin retains its Runtime-issued replay identity. Never put
        # it, SQL, raw inputs or driver exceptions in error text/log fields.
        self.usage_id = usage_id
        super().__init__()


class UsageSink(Protocol):
    def begin(self, operation: str, provider_label: str, pricing_context: Mapping[str, Any], *,
              usage_id: str | None = None, run_ref: Mapping[str, str] | None = None,
              run_ref_reason: str | None = None) -> str:
        """Durably STARTED immediately before HTTP; failure means no HTTP.

        Omit usage_id for a new invocation. Replay accepts only an identity
        previously issued by this sink (returned or on begin persistence error).
        A replay is persistence-only, never permission to repeat completed HTTP.
        run_ref is a planned ID, not evidence of a produced Run. Explicit
        null + DIRECT_NO_RUN declares an invocation with no logical Run concept.
        Omitted intent remains unresolved by automatic reconciliation.
        """
        ...

    def finish(self, usage_id: str, *, token_usage: Mapping[str, Any] | None,
               processed_duration_sec: float | None, latency_ms: int | None,
               pricing_context: Mapping[str, Any], cost: Mapping[str, Any],
               outcome: str, failure_kind: str | None = None) -> None:
        """Persist actual observation before Run construction, even on failure.

        Keep these facts for persistence replay; never re-invoke provider HTTP.
        This method does not finalize or discard observations on ownership loss.
        """
        ...

    def finalize(self, usage_id: str, *, run_ref: Mapping[str, str] | None,
                 run_ref_reason: str | None) -> None:
        """Caller confirms actual Run relationship; FAILED Runs still link.

        Explicit null + RUN_NOT_PRODUCED means the Run was actually not created;
        DIRECT_NO_RUN means there was no logical Run concept, including in a job.
        Final append and tracker marking commit together; only OBSERVED is legal.
        """
        ...
