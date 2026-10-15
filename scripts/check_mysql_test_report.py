#!/usr/bin/env python3
"""Fail closed on skipped, xfailed, deselected, absent or incomplete MySQL tests."""

import json
from pathlib import Path
import sys
from xml.etree import ElementTree

REQUIRED_SCENARIOS = frozenset({
    "sessions", "session_replacements", "worker_1205", "worker_1213",
    "worker_disconnect", "worker_exhaustion", "capability_boundary",
    "api_precommit", "commit_response_loss", "worker_unknown_commit",
    "pool_exhaustion", "dedicated_connections", "idle_recycle", "wait_timeout",
    "case_compatibility", "migration_policy", "require_privileges",
})

# Stable acceptance identifiers, independent of Python test function names.
REQUIRED_CHECKS = frozenset({
    ("api_health", "ready"), ("api_health", "storage"), ("api_health", "process"),
    *(("usage_reconciliation", scenario) for scenario in (
        "relation", "late", "concurrent", "isolation", "db_clock", "projection", "worker",
        "process_kill", "commit_unknown", "retry", "migration", "direct", "intent")),
    *(("usage_sink", scenario) for scenario in (
        "invocations", "replay", "conflict", "atomicity", "concurrent", "commit_unknown",
        "state", "no_run", "retry", "worker", "validation")),
    *(("redelivery", scenario) for scenario in (
        "eligibility", "atomicity", "concurrent", "commit_unknown", "isolation",
        "unsupported", "metric", "startup_periodic", "process_kill")),
    # RT-07(a): Final persistence, without sink/reconciliation wiring.
    *(("usage", scenario) for scenario in (
        "schema", "migration", "checks", "references", "amount", "binding", "append",
        "duplicate", "concurrent", "commit_unknown", "validation")),
    *(("sweep", scenario) for scenario in ("detect_latency", "detect_boundary", "detect_fault")),
    ("sweep_worker", "hook_fatal"), ("sweep_worker", "hook_exception"),
    *(("sweep", scenario) for scenario in (
        "atomicity", "eligibility", "cap_cancel", "backoff", "concurrent", "recheck",
        "rollback_retry", "unknown_commit", "cancel_race", "expiry", "metrics")),
    *(("sweep_worker", scenario) for scenario in ("startup", "independent", "heartbeat", "queue_wait", "slow_queue_logger")),
    ("cancel_worker", "terminal_ack"),
    ("cancel_worker", "observe_commit"), ("cancel_worker", "queued_no_usage"),
    *(("cancel", scenario) for scenario in (
        "states", "transaction", "claim_race", "sweep_race", "finish_race", "lock_order", "validation", "sweep_pending")),
    *(("cancel_worker", scenario) for scenario in (
        "observe", "late_success", "ownership", "heartbeat_error", "cleanup", "db_clock", "observation_fault")),
    ("heartbeat_lifecycle", "owned_cleanup"),
    *(("heartbeat_lifecycle", scenario) for scenario in (
        "renewal", "zero_rows", "commit_race", "retry_fence", "cleanup", "slow_attempt", "error_isolation", "connection_fault", "zero_commit_failure")),
    # RT-04(b): T2 delivery, atomicity, retry and fake E2E-0.
    *(("worker_t2", scenario) for scenario in (
        "delivery", "rollback", "t1_gap", "commit_recovery", "metric",
        "zero_guard", "sink_isolation", "e2e0", "recovery")),
    ("api", "sessions"), ("worker", "sessions"),
    ("api", "idle_recycle"), ("worker", "idle_recycle"),
    ("api", "disconnect_replacement"), ("worker", "disconnect_replacement"),
    ("api", "wait_timeout"), ("worker", "wait_timeout"),
    ("api", "pool_exhaustion"), ("heartbeat", "sessions"),
    ("heartbeat", "dedicated_connections"), ("ready", "dedicated_connections"),
    ("migration", "migration_policy"), ("api", "connect_failure"),
    ("worker", "worker_1205"), ("worker", "worker_1213"),
    ("worker", "worker_disconnect"), ("worker", "worker_exhaustion"),
    ("worker", "capability_boundary"), ("worker", "worker_unknown_commit"),
    ("api", "precommit_1205"), ("api", "precommit_disconnect"),
    ("api", "precommit_proxy_disconnect"), ("api", "commit_response_loss"),
    ("api", "commit_response_loss_context_exit"), ("api", "commit_response_loss_pool_checkin"),
    ("harness", "require_privileges"), ("case", "case_compatibility"),
    ("harness", "schema_identity"), ("harness", "schema_override_database"),
    ("harness", "schema_override_db"), ("harness", "schema_override_init_command"),
    # RT-02(b): keep RT-02(a)'s 32 role checks and Case inventory intact.
    ("migration", "case_external_transaction"), ("migration", "case_url_precedence"),
    ("migration", "case_offline_precedence"), ("migration", "empty_schema"),
    ("migration", "idempotency"), ("migration", "explicit_target"),
    ("migration", "first_runtime_revision"), ("migration", "partial_failure"),
    ("migration", "revision_preflight"), ("migration", "process_guard"),
    ("migration", "cli_stdin"),
    # RT-03(a): require execution evidence, even if the entire jobs suite is omitted.
    ("jobs", "schema"), ("jobs", "enqueue_rollback"), ("jobs", "enqueue_duplicate"),
    ("jobs", "read_contract"), ("jobs", "read_states"),
    # RT-03(b): queue, receipt, terminal, UTC and measurement acceptance.
    ("jobs", "token_migration"),
    ("jobs", "claim_basic"),
    ("jobs", "claim_eligibility"),
    ("jobs", "claim_empty"),
    ("jobs", "claim_concurrent"),
    ("jobs", "claim_skip_locked"),
    ("jobs", "claim_commit_boundary"),
    ("jobs", "claim_no_insert"),
    ("jobs", "claim_index"),
    ("jobs", "finish_targets"),
    ("jobs", "finish_guard"),
    ("jobs", "finish_rollback"),
    ("jobs", "finish_rejection"),
    ("jobs", "finish_validation"),
    ("jobs", "claim_unknown_commit"),
    ("jobs", "claim_token_identity"),
    ("jobs", "claim_disconnect"),
    ("jobs", "finish_race"),
    ("jobs", "claim_rc_finish"),
    ("jobs", "finish_deadlock"),
    ("jobs", "claim_lock_timeout"),
    ("jobs", "claim_latency"),
    ("api", "utc_session"), ("worker", "utc_session"),
    # RT-04(a): Worker composition must execute on real MySQL in CI.
    ("worker_core", "success"), ("worker_core", "failure"),
    ("worker_core", "claim_db_recovery"), ("worker_core", "terminal_db_recovery"),
    ("worker_core", "terminal_unknown_commit"), ("worker_core", "finish_rejected"),
    ("worker_core", "correlation"),
    ("worker_core", "logger_isolation"),
})

# Each parameter is an independent acceptance obligation. Names come from
# explicit pytest marks, never from function names or parsed node ID suffixes.
REQUIRED_PARAMETERS = frozenset({
    *(("api_health", "ready", mode) for mode in ("normal", "pool_exhausted", "connection_lost", "server_stopped")),
    ("api_health", "storage", "readonly"), ("api_health", "process", "single_worker"),
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
    *(("usage_sink", "replay", stage) for stage in ("begin", "finish", "finalize")),
    *(("usage_sink", "conflict", mode) for mode in
      ("token", "cost", "pricing", "outcome", "duration", "latency", "failure", "run", "null_run")),
    *(("usage_sink", "atomicity", mode) for mode in ("append", "marker", "commit", "rollback")),
    *(("usage_sink", "concurrent", mode) for mode in
      ("finish_same", "finish_conflict", "finalize_same", "finalize_conflict", "finish_finalize")),
    *(("usage_sink", "commit_unknown", stage + suffix) for stage in ("begin", "finish", "finalize")
      for suffix in ("", "_exhausted")),
    *(("usage_sink", "retry", f"{stage}_{code}") for stage in ("begin", "finish", "finalize") for code in (1205, 1213)),
    *(("usage_sink", "worker", mode) for mode in ("isolation", "begin_failure", "finish_failure", "cancel", "ownership")),
    *(("usage_sink", "validation", mode) for mode in
      ("token", "total", "duration", "latency", "pricing", "float", "currency", "outcome", "failure", "extra", "run", "direct_no_run")),
    *(("redelivery", "eligibility", mode) for mode in
      ("SUCCEEDED", "FAILED", "CANCELLED", "STALE", "QUEUED", "RUNNING", "receipt")),
    *(("redelivery", "atomicity", mode) for mode in ("success", "failed_hint", "enqueue", "marker")),
    ("redelivery", "concurrent", "case_first"),
    *(("redelivery", "commit_unknown", mode) for mode in ("followup", "stopped")),
    *(("redelivery", "isolation", mode) for mode in ("reflector", "db", "logger", "filter", "handler", "scan")),
    *(("redelivery", "unsupported", mode) for mode in ("PLATE_READ", "UNKNOWN")),
    *(("redelivery", "metric", mode) for mode in
      ("first_stopped", "retry_stopped", "third_stopped", "CANCELLED", "SUPERSEDED", "APPLIED")),
    *(("redelivery", "startup_periodic", mode) for mode in ("startup", "periodic")),
    *(("redelivery", "process_kill", mode) for mode in ("gap", "running")),
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
    *(("sweep", "detect_latency", f"{lease}_{reason}") for lease in (60, 7)
      for reason in ("RETRIED", "EXHAUSTED", "CANCELLED")),
    *(("sweep", "detect_boundary", mode) for mode in ("transition_clock", "null", "future")),
    *(("sweep", "detect_fault", mode) for mode in ("calculation", "logger", "filter", "handler")),
    *(("sweep_worker", "hook_fatal", f"{phase}_{kind}_{sink}") for phase in ("startup", "periodic")
      for kind in ("exit", "interrupt", "base") for sink in ("healthy", "logger", "filter", "handler")),
    ("sweep_worker", "hook_exception", "startup_periodic"),
    *(("sweep_worker", "queue_wait", mode) for mode in ("1", "2")),
    *(("sweep", "atomicity", mode) for mode in ("commit", "rollback")),
    *(("sweep", "cap_cancel", mode) for mode in ("cancel", "exhausted", "disabled")),
    *(("sweep", "recheck", mode) for mode in ("heartbeat", "finish", "cancel")),
    *(("sweep", "cancel_race", mode) for mode in ("sweep", "cancel")),
    *(("cancel_worker", "terminal_ack", mode) for mode in
      ("commit_delay", "slow_logger", "lock_wait", "unknown_commit", "retry",
       "logger", "filter", "handler", "calculation", "zero_rows")),
    *(("cancel", "states", state) for state in
      ("QUEUED", "RUNNING", "STALE", "SUCCEEDED", "FAILED", "CANCELLED")),
    *(("cancel", "transaction", mode) for mode in ("commit", "rollback")),
    *(("cancel", "claim_race", mode) for mode in ("cancel", "claim", "concurrent")),
    *(("cancel", "sweep_race", mode) for mode in ("sweep", "cancel")),
    *(("cancel", "finish_race", mode) for mode in ("SUCCEEDED", "CANCELLED", "marker")),
    *(("cancel_worker", "observe", sink) for sink in
      ("healthy", "logger", "filter", "handler", "observer")),
    *(("cancel_worker", "ownership", mode) for mode in ("ownership", "cancel")),
    *(("cancel_worker", "cleanup", mode) for mode in
      ("success", "failure", "exception", "interrupt", "exit", "cancel")),
    *(("cancel_worker", "observation_fault", fault) for fault in ("read", "commit")),
    *(("heartbeat_lifecycle", "retry_fence", mode) for mode in ("transaction", "loop")),
    *(("heartbeat_lifecycle", "owned_cleanup", mode) for mode in
      ("success", "heartbeat_interrupt", "handler_interrupt")),
    *(("heartbeat_lifecycle", "zero_rows", sink) for sink in
      ("healthy", "logger", "filter", "handler", "observer")),
    *(("heartbeat_lifecycle", "connection_fault", fault) for fault in ("disconnect", "timeout")),
    *(("heartbeat_lifecycle", "commit_race", mode) for mode in ("local_loss", "db_transfer")),
    *(("heartbeat_lifecycle", "cleanup", mode) for mode in
      ("success", "failure", "exception", "interrupt", "exit", "signal")),
    *(("heartbeat_lifecycle", "error_isolation", sink) for sink in
      ("healthy", "logger", "filter", "handler", "observer")),
    *(("worker_t2", "delivery", outcome) for outcome in
      ("APPLIED", "ALREADY_APPLIED", "STOPPED_WAITING", "CANCELLED", "SUPERSEDED")),
    *(("worker_t2", "rollback", fault) for fault in
      ("reflector", "enqueue", "extra", "tampered_reason", "non_applied_jobs", "cross_case", "commit", "rollback")),
    *(("worker_t2", "t1_gap", status) for status in ("SUCCEEDED", "FAILED")),
    *(("worker_t2", "commit_recovery", outcome) for outcome in ("APPLIED", "STOPPED_WAITING")),
    *(("worker_t2", "metric", mode) for mode in
      ("first_stopped", "retry_stopped", "third_stopped", "cancelled", "superseded", "already", "applied", "exception")),
    *(("worker_t2", "zero_guard", mode) for mode in ("missing", "mismatch", "zero", "already", "insert_then_marker_failure")),
    *(("worker_t2", "sink_isolation", mode + "_" + sink)
      for mode in ("metric", "failure", "db_retry") for sink in ("filter", "handler")),
    *(("worker_t2", "recovery", mode) for mode in ("exhausted", "next_job", "concurrent", "exhausted_next_job")),
    *(("worker_core", "logger_isolation", scenario + "_" + sink)
      for scenario in ("started", "completed", "claim_db", "terminal_db") for sink in ("filter", "handler")),
    *(("worker_core", "failure", mode) for mode in ("unknown", "module", "exception", "invalid")),
    *(("worker_core", "terminal_unknown_commit", status) for status in ("SUCCEEDED", "FAILED")),
    *(("worker_core", "correlation", mode) for mode in ("max_job_id", "path_id")),
    ("jobs", "read_states", "QUEUED"), ("jobs", "read_states", "RUNNING"),
    ("jobs", "read_states", "SUCCEEDED"), ("jobs", "read_states", "FAILED"),
    ("jobs", "read_states", "STALE"), ("jobs", "read_states", "CANCELLED"),
    ("jobs", "enqueue_duplicate", "separate_batch"),
    ("jobs", "enqueue_duplicate", "same_batch"),
    ("jobs", "claim_eligibility", "past"),
    ("jobs", "claim_eligibility", "equal"),
    ("jobs", "claim_eligibility", "future"),
    ("jobs", "claim_empty", "empty"),
    ("jobs", "claim_empty", "all_locked"),
    ("jobs", "finish_targets", "SUCCEEDED"),
    ("jobs", "finish_targets", "FAILED"),
    ("jobs", "finish_targets", "CANCELLED"),
    ("jobs", "finish_guard", "missing"),
    ("jobs", "finish_guard", "other_owner"),
    ("jobs", "finish_guard", "QUEUED"),
    ("jobs", "finish_guard", "SUCCEEDED"),
    ("jobs", "finish_guard", "FAILED"),
    ("jobs", "finish_guard", "CANCELLED"),
    ("jobs", "finish_guard", "STALE"),
    ("jobs", "finish_rejection", "STALE"),
    ("jobs", "finish_rejection", "QUEUED"),
    ("jobs", "finish_rejection", "RUNNING"),
    ("jobs", "finish_rejection", "UNKNOWN"),
    ("jobs", "claim_unknown_commit", "recovered"),
    ("jobs", "claim_unknown_commit", "token"),
    ("jobs", "claim_unknown_commit", "owner"),
    ("jobs", "claim_unknown_commit", "terminal"),
    ("jobs", "claim_unknown_commit", "expired"),
    ("jobs", "claim_unknown_commit", "missing"),
    ("jobs", "finish_race", "SUCCEEDED_commit"),
    ("jobs", "finish_race", "SUCCEEDED_rollback"),
    ("jobs", "finish_race", "FAILED_commit"),
    ("jobs", "finish_race", "FAILED_rollback"),
    ("jobs", "finish_race", "CANCELLED_commit"),
    ("jobs", "finish_race", "CANCELLED_rollback"),
    ("jobs", "claim_rc_finish", "FAILED"),
    ("jobs", "claim_rc_finish", "CANCELLED"),
    ("api", "utc_session", "fresh"),
    ("api", "utc_session", "reused"),
    ("api", "utc_session", "replacement"),
    ("worker", "utc_session", "fresh"),
    ("worker", "utc_session", "reused"),
    ("worker", "utc_session", "replacement"),
})

# Pin the merged Case coverage without editing Case-owned tests/fixtures.
# Future intentional test renames update this inventory alongside that change.
REQUIRED_CASE_TESTS = {
    "tests/case/test_store_mysql.py": {
        "test_migration_creates_case_tables_with_ascii_bin_ids": 1,
        "test_rollback_leaves_nothing": 1,
        "test_update_lock_makes_second_writer_wait": 1,
        "test_repository_never_commits": 1,
        "test_append_only_violation_writes_nothing_even_if_caller_commits": 1,
    },
    "tests/case/test_case_repository_contract.py": {
        "test_insert_then_load_round_trips": 1,
        "test_load_returns_a_new_object_each_time": 1,
        "test_save_persists_changes_and_appended_records": 1,
        "test_save_refuses_changed_prefix": 1,
        "test_save_refuses_removed_record": 1,
        "test_load_missing_case_is_key_error": 1,
        "test_insert_twice_is_refused": 1,
        "test_case_ids_differ_by_case_only_are_distinct": 1,
        "test_invalid_case_id_is_refused_before_insert": 3,
        "test_tuple_in_state_round_trips_as_list": 1,
        "test_non_json_value_in_state_is_refused": 1,
    },
}


def validate_report(report):
    if not str(report.get("server_version", "")).startswith("8.4."):
        raise ValueError("real MySQL 8.4 preflight evidence missing")
    collected = report.get("collected", [])
    expected = {item["nodeid"] for item in collected}
    if not expected or len(expected) != len(collected):
        raise ValueError("MySQL collection is empty or duplicated")
    if expected != set(report.get("selected", [])):
        raise ValueError("MySQL tests were deselected or selection evidence is missing")
    if report.get("collection_errors"):
        raise ValueError("test collection had errors/skips")
    try:
        checks = {(check["role"], check["scenario"]) for item in collected for check in item.get("checks", [])}
        parameters = {(check["role"], check["scenario"], check["parameter"])
                      for item in collected for check in item.get("checks", []) if "parameter" in check}
    except (KeyError, TypeError):
        raise ValueError("invalid MySQL role/scenario evidence") from None
    if REQUIRED_CHECKS - checks:
        raise ValueError("required MySQL role/scenario missing")
    if REQUIRED_PARAMETERS - parameters:
        raise ValueError("required MySQL role/scenario/parameter missing")
    scenarios = {value for item in collected for value in item.get("scenarios", [])}
    if REQUIRED_SCENARIOS - scenarios:
        raise ValueError("required MySQL scenarios missing: " + ", ".join(sorted(REQUIRED_SCENARIOS - scenarios)))
    for path, functions in REQUIRED_CASE_TESTS.items():
        for function, minimum in functions.items():
            count = sum(node.split("::")[0] == path and node.split("::")[-1].split("[")[0] == function
                        for node in expected)
            if count < minimum:
                raise ValueError("Case MySQL test coverage missing: " + function)
    phases = {}
    for item in report.get("reports", []):
        if item["nodeid"] not in expected:
            raise ValueError("uncollected MySQL execution")
        if item["outcome"] != "passed" or item.get("xfail"):
            raise ValueError("MySQL tests must pass: skip/xfail/failure/error forbidden")
        key = (item["nodeid"], item["when"])
        if key in phases:
            raise ValueError("duplicate MySQL execution phase")
        phases[key] = True
    if set(phases) != {(node, phase) for node in expected for phase in ("setup", "call", "teardown")}:
        raise ValueError("MySQL execution phases missing")
    return len(expected)


def validate_junit(path, report):
    # The plugin records JUnit's classname/name pair, avoiding lossy nodeid parsing.
    cases = {(case.get("classname"), case.get("name")): case
             for case in ElementTree.parse(path).findall(".//testcase")}
    for item in report["collected"]:
        key = tuple(item["junit"])
        if key not in cases:
            raise ValueError("MySQL testcase missing from JUnit")
        if any(cases[key].find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise ValueError("MySQL JUnit contains skip/failure/error")


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    try:
        report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        count = validate_report(report)
        if len(args) > 1:
            validate_junit(args[1], report)
    except (OSError, ValueError, KeyError, TypeError, IndexError, ElementTree.ParseError):
        print("MySQL execution gate FAILED: incomplete or invalid evidence", file=sys.stderr)
        return 1
    print(f"MySQL execution gate PASS: {count} tests, skip=0, xfail=0; required scenarios present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
