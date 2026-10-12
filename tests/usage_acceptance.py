"""Independent RT-07(a) acceptance inventory, never imported by production gate."""

USAGE_CHECKS = tuple(("usage", name) for name in (
    "schema", "migration", "checks", "references", "amount", "binding", "append",
    "duplicate", "concurrent", "commit_unknown", "validation",
))

USAGE_PARAMETERS = (
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
