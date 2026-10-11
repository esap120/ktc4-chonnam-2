"""Public pure-function boundary for the evidence module."""

from .assembly import assemble_evidence, calculate_evidence_needs, resolve_independent_facts
from .corrections import correction_heads
from .disposition import (
    ASSEMBLE,
    AWAIT_SITUATION_RESPONSE,
    NOT_ASSEMBLED,
    VisualEvidenceDisposition,
    classify_visual_evidence,
)
from .errors import (
    ContractInputError,
    EvidenceError,
    PackageNotReady,
    PolicyConfigurationError,
    VisualEventNotAssembled,
)
from .policy import EVENT_POLICY, SAFETY_REPORT_POLICY_REF, render_report
from .requirements import (
    aggregate_outcomes,
    build_report_package,
    evaluate_requirements,
)
from .time_resolution import resolve_time
from .validation import validate_contract

__all__ = [
    "ASSEMBLE",
    "AWAIT_SITUATION_RESPONSE",
    "EVENT_POLICY",
    "NOT_ASSEMBLED",
    "SAFETY_REPORT_POLICY_REF",
    "ContractInputError",
    "EvidenceError",
    "PackageNotReady",
    "PolicyConfigurationError",
    "VisualEventNotAssembled",
    "VisualEvidenceDisposition",
    "aggregate_outcomes",
    "assemble_evidence",
    "build_report_package",
    "calculate_evidence_needs",
    "classify_visual_evidence",
    "correction_heads",
    "evaluate_requirements",
    "render_report",
    "resolve_independent_facts",
    "resolve_time",
    "validate_contract",
]
