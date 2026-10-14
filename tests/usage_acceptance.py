"""Independent RT-07 acceptance inventory, never imported by production gate."""

USAGE_CHECKS = tuple(("usage", name) for name in (
    "schema", "migration", "checks", "references", "amount", "binding", "append",
    "duplicate", "concurrent", "commit_unknown", "validation",
)) + tuple(("usage_sink", name) for name in (
    "invocations", "replay", "conflict", "atomicity", "concurrent", "commit_unknown", "state", "no_run", "retry", "worker", "validation",
))

USAGE_PARAMETERS = (
    *(("usage_sink", "replay", stage) for stage in ("begin", "finish", "finalize")),
    *(("usage_sink", "conflict", mode) for mode in
      ("token", "cost", "pricing", "outcome", "duration", "latency", "failure", "run", "null_run")),
    *(("usage_sink", "atomicity", mode) for mode in ("append", "marker", "commit", "rollback")),
    *(("usage_sink", "concurrent", mode) for mode in
      ("finish_same", "finish_conflict", "finalize_same", "finalize_conflict", "finish_finalize")),
    *(("usage_sink", "commit_unknown", stage + suffix) for stage in ("begin", "finish", "finalize")
      for suffix in ("", "_exhausted")),
    *(("usage_sink", "validation", mode) for mode in
      ("token", "total", "duration", "latency", "pricing", "float", "currency", "outcome", "failure", "extra", "run", "direct_no_run")),
    *(("usage_sink", "retry", f"{stage}_{code}") for stage in ("begin", "finish", "finalize") for code in (1205, 1213)),
    *(("usage_sink", "worker", mode) for mode in ("isolation", "begin_failure", "finish_failure", "cancel", "ownership")),
    *(("usage", "checks", f"{table}_{mode}") for table in ("usage_record", "usage_inflight")
      for mode in ("partial_input", "partial_output", "partial_total", "only_input", "only_output", "only_total",
                   "sum", "currency", "lower_currency", "run_kind", "run_partial", "run_reason", "reason_invalid",
                   "run_kind_space", "reason_space")),
    ("usage", "checks", "usage_inflight_state_space"), ("usage", "checks", "usage_inflight_outcome_space"),
    ("usage", "checks", "usage_record_reason_missing"),
    *(("usage", "amount", mode) for mode in ("null", "zero", "example", "tiny", "max", "negative")),
    *(("usage", "binding", f"{table}_{mode}") for table in ("usage_record", "usage_inflight")
      for mode in ("float", "integer", "precision", "scale", "zero_scale", "nonfinite")),
    *(("usage", "append", mode) for mode in ("commit", "rollback")),
    *(("usage", "duplicate", mode) for mode in
      ("direct_pk", "identical", "amount", "null_zero", "run", "pricing", "context", "token", "latency", "provider")),
    *(("usage", "concurrent", mode) for mode in ("commit", "rollback", "conflict")),
    *(("usage", "commit_unknown", mode) for mode in ("manual", "worker")),
    *(("usage", "validation", mode) for mode in
      ("float", "scale", "precision", "currency", "token", "sum", "run", "extra", "nested_extra", "identity", "naive_time", "transaction")),
)

USAGE_CHECKS += tuple(("usage_reconciliation", scenario) for scenario in (
    "relation", "late", "concurrent", "isolation", "db_clock", "projection", "worker",
    "process_kill", "commit_unknown", "retry", "migration", "direct", "intent",
))
USAGE_PARAMETERS += (
    *(("usage_reconciliation", "relation", mode) for mode in (
        "SUCCEEDED", "FAILED", "CANCELLED", "STALE", "absent", "different", "direct_no_run",
        "unknown", "RUNNING", "QUEUED", "missing", "cross_case", "invalid_produced")),
    *(("usage_reconciliation", "late", mode) for mode in (
        "unobserved", "observed", "direct_no_run", "replay", "conflict", "relationship")),
    *(("usage_reconciliation", "concurrent", mode) for mode in (
        "reconcilers", "normal_recovery", "late_same", "late_conflict")),
    *(("usage_reconciliation", "isolation", mode) for mode in (
        "logger", "observer", "late_logger", "late_observer", "metrics")),
    ("usage_reconciliation", "db_clock", "oldest"),
    ("usage_reconciliation", "projection", "final_only"),
    *(("usage_reconciliation", "worker", mode) for mode in ("normal_t1", "startup", "periodic", "finish_persistence_replay")),
    *(("usage_reconciliation", "process_kill", mode) for mode in ("startup", "periodic")),
    *(("usage_reconciliation", "commit_unknown", stage + suffix)
      for stage in ("recovery", "late") for suffix in ("", "_exhausted")),
    *(("usage_reconciliation", "retry", f"{stage}_{code}")
      for stage in ("recovery", "late") for code in (1205, 1213)),
    ("usage_reconciliation", "migration", "legacy"),
    ("usage_reconciliation", "direct", "explicit_finalize"),
    *(("usage_reconciliation", "intent", mode) for mode in (
        "planned_replay", "direct_replay", "different_run", "different_reason", "premature_not_produced")),
)
