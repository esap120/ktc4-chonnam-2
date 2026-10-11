"""Check omissions against an actual complete MySQL report, not fabricated evidence."""

from copy import deepcopy
import importlib.util
import json
import os
import subprocess
import sys
from xml.etree import ElementTree

import pytest

from migration_support import ROOT

pytestmark = pytest.mark.mysql

# Independent acceptance inventory, not imported from the gate under test.
MIGRATION_CHECKS = (
    "case_external_transaction", "case_url_precedence", "case_offline_precedence",
    "empty_schema", "idempotency", "explicit_target", "first_runtime_revision",
    "partial_failure", "revision_preflight", "process_guard", "cli_stdin",
)

LIFECYCLE_CHECKS = (
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
)

WORKER_CHECKS = (
    ("heartbeat_lifecycle", "owned_cleanup"),
    *(("heartbeat_lifecycle", scenario) for scenario in (
        "renewal", "zero_rows", "commit_race", "retry_fence", "cleanup", "slow_attempt", "error_isolation", "connection_fault", "zero_commit_failure")),
    # RT-04(b): T2 delivery, atomicity, retry and fake E2E-0.
    *(("worker_t2", scenario) for scenario in (
        "delivery", "rollback", "t1_gap", "commit_recovery", "metric",
        "zero_guard", "sink_isolation", "e2e0", "recovery")),
    ("worker_core", "success"), ("worker_core", "failure"),
    ("worker_core", "claim_db_recovery"), ("worker_core", "terminal_db_recovery"),
    ("worker_core", "terminal_unknown_commit"), ("worker_core", "finish_rejected"),
    ("worker_core", "correlation"),
    ("worker_core", "logger_isolation"),
)

WORKER_PARAMETERS = (
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
)

JOB_PARAMETERS = (
    *(("jobs", "read_states", state) for state in
      ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "STALE", "CANCELLED")),
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
)


def test_actual_report_rejects_each_missing_migration_check(mysql_schema_url, tmp_path):
    report_path = tmp_path / "mysql.json"
    junit_path = tmp_path / "mysql.xml"
    env = dict(os.environ, DAESINGO_MYSQL_URL=mysql_schema_url.render_as_string(hide_password=False),
               DAESINGO_REQUIRE_MYSQL="1", PYTHONDONTWRITEBYTECODE="1")
    # Exclude this test to avoid recursion. Use a separate disposable base schema
    # so legacy Case initialization cannot alter the parent suite's database.
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "tests/common/db/integration", "tests/common/jobs",
         "tests/worker/test_worker_mysql.py", "tests/worker/test_reflection_mysql.py",
         "tests/worker/test_heartbeat_mysql.py",
         "tests/case/test_store_mysql.py", "tests/case/test_case_repository_contract.py",
         "--ignore=tests/common/db/integration/test_migration_gate.py", "-m", "mysql", "-q",
         "-p", "no:cacheprovider", f"--basetemp={tmp_path / 'child'}",
         f"--mysql-report={report_path}", f"--junitxml={junit_path}"],
        # This repeats the complete MySQL inventory, including migrations for
        # each fixture. Allow slower local servers without relaxing the gate.
        env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("real_report_gate", ROOT / "scripts/check_mysql_test_report.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.validate_report(report)
    gate.validate_junit(junit_path, report)
    for role, scenario in [*( ("migration", scenario) for scenario in MIGRATION_CHECKS),
                           ("jobs", "schema"), ("jobs", "enqueue_rollback"),
                           ("jobs", "enqueue_duplicate"), ("jobs", "read_contract"), ("jobs", "read_states"),
                           *LIFECYCLE_CHECKS, *WORKER_CHECKS]:
        broken = deepcopy(report)
        removed = {item["nodeid"] for item in broken["collected"]
                   if any(c["role"] == role and c["scenario"] == scenario for c in item.get("checks", []))}
        assert removed, scenario
        broken["collected"] = [item for item in broken["collected"] if item["nodeid"] not in removed]
        broken["selected"] = [node for node in broken["selected"] if node not in removed]
        broken["reports"] = [item for item in broken["reports"] if item["nodeid"] not in removed]
        with pytest.raises(ValueError, match="role/scenario"):
            gate.validate_report(broken)

    # Keep every other parameter in place. A family-level set check would
    # incorrectly accept the "all" mutation, including deletion from JUnit.
    mutations = []
    for role, scenario, parameter in (*JOB_PARAMETERS, *WORKER_PARAMETERS):
        check = {"role": role, "scenario": scenario, "parameter": parameter}
        entry, = (n for n in report["collected"] if check in n.get("checks", []))
        node = entry["nodeid"]
        for layer in ("collection", "selection", "setup", "call", "teardown", "all", "junit"):
            broken = deepcopy(report)
            if layer in {"collection", "all"}:
                broken["collected"] = [n for n in broken["collected"] if n["nodeid"] != node]
            if layer in {"selection", "all"}:
                broken["selected"].remove(node)
            if layer in {"setup", "call", "teardown", "all"}:
                broken["reports"] = [r for r in broken["reports"]
                                     if r["nodeid"] != node or (layer != "all" and r["when"] != layer)]
            xml = ElementTree.parse(junit_path)
            if layer in {"junit", "all"}:
                matches = 0
                for parent in xml.iter():
                    for case in list(parent):
                        if case.tag == "testcase" and (case.get("classname"), case.get("name")) == tuple(entry["junit"]):
                            parent.remove(case)
                            matches += 1
                assert matches == 1
            mutation_junit = tmp_path / f"{scenario}-{parameter}-{layer}.xml"
            xml.write(mutation_junit, encoding="utf-8")
            with pytest.raises(ValueError):
                gate.validate_report(broken)
                gate.validate_junit(mutation_junit, broken)
            mutations.append({"role": role, "scenario": scenario, "parameter": parameter,
                              "layer": layer, "rejected": True})
    assert len(mutations) == (len(JOB_PARAMETERS) + len(WORKER_PARAMETERS)) * 7
    (tmp_path / "parameter-mutations.json").write_text(json.dumps(mutations, indent=2), encoding="utf-8")
