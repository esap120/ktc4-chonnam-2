"""Fail-closed harness/report behavior, independent of a MySQL server."""

import importlib.util
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from usage_acceptance import USAGE_CHECKS, USAGE_PARAMETERS
from redelivery_acceptance import REDELIVERY_CHECKS, REDELIVERY_PARAMETERS

ROOT = Path(__file__).resolve().parents[3]

# Independent role/scenario acceptance inventory, deliberately not imported
# from the implementation being tested. Test function names are irrelevant.
API_HEALTH_PARAMETERS = tuple(("api_health", scenario, parameter) for scenario, parameter in (
    ("ready", "normal"), ("ready", "pool_exhausted"), ("ready", "connection_lost"),
    ("ready", "server_stopped"), ("storage", "readonly"), ("process", "single_worker")))

REQUIRED_CHECKS = (
    *((role, scenario) for role, scenario, parameter in API_HEALTH_PARAMETERS),
    *REDELIVERY_CHECKS,
    *USAGE_CHECKS,
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
    ("migration", "case_external_transaction"), ("migration", "case_url_precedence"),
    ("migration", "case_offline_precedence"), ("migration", "empty_schema"),
    ("migration", "idempotency"), ("migration", "explicit_target"),
    ("migration", "first_runtime_revision"), ("migration", "partial_failure"),
    ("migration", "revision_preflight"), ("migration", "process_guard"),
    ("migration", "cli_stdin"),
    ("jobs", "schema"), ("jobs", "enqueue_rollback"), ("jobs", "enqueue_duplicate"),
    ("jobs", "read_contract"), ("jobs", "read_states"),
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
    ("worker_core", "success"), ("worker_core", "failure"),
    ("worker_core", "claim_db_recovery"), ("worker_core", "terminal_db_recovery"),
    ("worker_core", "terminal_unknown_commit"), ("worker_core", "finish_rejected"),
    ("worker_core", "correlation"),
    ("worker_core", "logger_isolation"),
)

REQUIRED_PARAMETERS = (
    *API_HEALTH_PARAMETERS,
    *REDELIVERY_PARAMETERS,
    *USAGE_PARAMETERS,
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
    *(("cancel_worker", "observation_fault", fault) for fault in ("read", "commit")),
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


def checker():
    path = ROOT / "scripts" / "check_mysql_test_report.py"
    spec = importlib.util.spec_from_file_location("mysql_report_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def good_report():
    nodes = [{"nodeid": f"tests/common/db/integration/test_required.py::test_{name}",
              "scenarios": [name]} for name in (
        "sessions", "session_replacements", "worker_1205", "worker_1213", "worker_disconnect",
        "worker_exhaustion", "capability_boundary", "api_precommit", "commit_response_loss",
        "worker_unknown_commit", "pool_exhaustion", "dedicated_connections", "idle_recycle",
        "wait_timeout", "case_compatibility", "migration_policy", "require_privileges")]
    # Explicit baseline inventory: do not derive expectations from the gate.
    nodes += [{"nodeid": "tests/case/test_store_mysql.py::" + name, "scenarios": []} for name in (
        "test_migration_creates_case_tables_with_ascii_bin_ids", "test_rollback_leaves_nothing",
        "test_update_lock_makes_second_writer_wait", "test_repository_never_commits",
        "test_append_only_violation_writes_nothing_even_if_caller_commits")]
    nodes += [{"nodeid": "tests/case/test_case_repository_contract.py::" + name + "[mysql]", "scenarios": []} for name in (
        "test_insert_then_load_round_trips", "test_load_returns_a_new_object_each_time",
        "test_save_persists_changes_and_appended_records", "test_save_refuses_changed_prefix",
        "test_save_refuses_removed_record", "test_load_missing_case_is_key_error", "test_insert_twice_is_refused",
        "test_case_ids_differ_by_case_only_are_distinct", "test_tuple_in_state_round_trips_as_list",
        "test_non_json_value_in_state_is_refused")]
    nodes += [{"nodeid": "tests/case/test_case_repository_contract.py::test_invalid_case_id_is_refused_before_insert[mysql-" + name + "]",
               "scenarios": []} for name in ("empty", "long", "unicode")]
    nodes += [{"nodeid": f"tests/common/db/integration/test_checks.py::test_check_{index}",
               "scenarios": [], "checks": [{"role": role, "scenario": scenario}]}
              for index, (role, scenario) in enumerate(REQUIRED_CHECKS)
              if not any((r, s) == (role, scenario) for r, s, p in REQUIRED_PARAMETERS)]
    # Deliberately opaque node IDs: policy must use stable check metadata.
    nodes += [{"nodeid": f"tests/common/jobs/test_checks.py::test_opaque_{index}",
               "scenarios": [], "checks": [
                   {"role": role, "scenario": scenario},
                   {"role": role, "scenario": scenario, "parameter": parameter}]}
              for index, (role, scenario, parameter) in enumerate(REQUIRED_PARAMETERS)]
    for index, node in enumerate(nodes):
        node["junit"] = ["opaque.module", f"case_{index}"]
    return {"server_version": "8.4.7", "collected": nodes,
            "selected": [n["nodeid"] for n in nodes], "collection_errors": [],
            "reports": [{"nodeid": n["nodeid"], "when": when, "outcome": "passed", "xfail": False}
                        for n in nodes for when in ("setup", "call", "teardown")]}


def test_report_accepts_complete_real_mysql_evidence():
    checker().validate_report(good_report())


@pytest.mark.parametrize("identity", [p for p in USAGE_PARAMETERS if p[0] == "usage_reconciliation"])
@pytest.mark.parametrize("field", ["role", "scenario", "parameter"])
def test_reconciliation_parameter_metadata_cannot_be_omitted(identity, field):
    report = good_report()
    role, scenario, parameter = identity
    expected = {"role": role, "scenario": scenario, "parameter": parameter}
    entry, = (n for n in report["collected"] if expected in n.get("checks", []))
    check, = (c for c in entry["checks"] if c == expected)
    del check[field]
    with pytest.raises(ValueError):
        checker().validate_report(report)


@pytest.mark.parametrize("scenario", ["renewal", "zero_rows", "commit_race", "retry_fence",
                                    "cleanup", "slow_attempt", "error_isolation", "connection_fault",
                                    "zero_commit_failure", "owned_cleanup"])
def test_heartbeat_acceptance_family_is_required(scenario):
    report = good_report()
    role = "heartbeat_lifecycle"
    removed = {n["nodeid"] for n in report["collected"] if any(
        c["role"] == role and c["scenario"] == scenario for c in n.get("checks", []))}
    report["collected"] = [n for n in report["collected"] if n["nodeid"] not in removed]
    report["selected"] = [n for n in report["selected"] if n not in removed]
    report["reports"] = [r for r in report["reports"] if r["nodeid"] not in removed]
    with pytest.raises(ValueError, match="role/scenario"):
        checker().validate_report(report)


@pytest.mark.parametrize("broken", ["empty", "skip", "xfail", "deselected", "missing_call", "missing_scenario", "collection", "wrong_server", "missing_case"])
def test_report_rejects_bypasses(broken):
    report = good_report()
    if broken == "empty":
        report["collected"] = []
    elif broken == "skip":
        report["reports"][0]["outcome"] = "skipped"
    elif broken == "xfail":
        report["reports"][1]["xfail"] = True
    elif broken == "deselected":
        report["selected"].pop()
    elif broken == "missing_call":
        report["reports"].pop(1)
    elif broken == "missing_scenario":
        report["collected"][0]["scenarios"] = []
    elif broken == "collection":
        report["collection_errors"] = ["test_store_mysql.py"]
    elif broken == "wrong_server":
        report["server_version"] = "8.0.40"
    elif broken == "missing_case":
        report["collected"] = [n for n in report["collected"] if "/case/" not in n["nodeid"]]
    with pytest.raises(ValueError):
        checker().validate_report(report)


def test_require_missing_url_fails_before_collection(tmp_path):
    env = dict(os.environ, DAESINGO_REQUIRE_MYSQL="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("DAESINGO_MYSQL_URL", None)
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                             "tests/common/db/test_engines.py", "--collect-only", "-q", "-p", "no:cacheprovider"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "DAESINGO_MYSQL_URL" in result.stdout + result.stderr
    assert "skipped" not in result.stdout


def test_require_missing_dependency_fails_without_skip(tmp_path):
    # A startup import blocker simulates an unavailable dependency in a child
    # process without uninstalling anything from the user's environment.
    (tmp_path / "sitecustomize.py").write_text(
        "import sys\nclass Block:\n def find_spec(self, fullname, *args):\n"
        "  if fullname == 'pymysql': raise ModuleNotFoundError('blocked dependency')\n"
        "sys.meta_path.insert(0, Block())\n", encoding="utf-8")
    env = dict(os.environ, DAESINGO_REQUIRE_MYSQL="1", DAESINGO_MYSQL_URL="mysql+pymysql://t:p@127.0.0.1/test_db",
               PYTHONPATH=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                             "tests/common/db/test_engines.py", "--collect-only", "-q", "-p", "no:cacheprovider"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "MySQL required dependency unavailable" in result.stdout + result.stderr
    assert "skipped" not in result.stdout


def test_require_connection_failure_is_an_error_not_skip():
    env = dict(os.environ, DAESINGO_REQUIRE_MYSQL="1", PYTHONDONTWRITEBYTECODE="1",
               DAESINGO_MYSQL_URL="mysql+pymysql://t:p@127.0.0.1:1/test_db")
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                             "tests/common/db/test_engines.py", "--collect-only", "-q", "-p", "no:cacheprovider"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "MySQL preflight failed" in result.stdout + result.stderr
    assert "skipped" not in result.stdout


def test_require_url_option_failure_is_sanitized_before_connect():
    secret = "private-timeout-value"
    env = dict(os.environ, DAESINGO_REQUIRE_MYSQL="1", PYTHONDONTWRITEBYTECODE="1",
               DAESINGO_MYSQL_URL="mysql+pymysql://t:p@127.0.0.1/test_db?connect_timeout=" + secret)
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                             "tests/common/db/test_engines.py", "--collect-only", "-q", "-p", "no:cacheprovider"],
                            cwd=ROOT, env=env, text=True, encoding="utf-8", capture_output=True, timeout=30)
    assert result.returncode != 0
    assert "MySQL preflight failed" in result.stdout + result.stderr
    assert secret not in result.stdout + result.stderr
    assert "skipped" not in result.stdout


def test_report_cli_fails_on_missing_artifact(tmp_path):
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/check_mysql_test_report.py"),
                             str(tmp_path / "missing.json")], text=True, capture_output=True, timeout=15)
    assert result.returncode != 0


def test_gate_rejects_partial_case_file_even_when_every_selected_test_passes():
    report = good_report()
    removed = next(item["nodeid"] for item in report["collected"]
                   if "test_invalid_case_id_is_refused_before_insert[mysql-unicode]" in item["nodeid"])
    report["collected"] = [item for item in report["collected"] if item["nodeid"] != removed]
    report["selected"].remove(removed)
    report["reports"] = [item for item in report["reports"] if item["nodeid"] != removed]
    with pytest.raises(ValueError, match="Case"):
        checker().validate_report(report)


@pytest.mark.parametrize("role,scenario", REQUIRED_CHECKS)
def test_each_required_role_check_is_mandatory_even_with_same_scenario_elsewhere(role, scenario):
    report = deepcopy(good_report())
    removed = {item["nodeid"] for item in report["collected"]
               if {"role": role, "scenario": scenario} in item.get("checks", [])}
    assert len(removed) == (sum((r, s) == (role, scenario) for r, s, p in REQUIRED_PARAMETERS) or 1)
    report["collected"] = [item for item in report["collected"] if item["nodeid"] not in removed]
    report["selected"] = [node for node in report["selected"] if node not in removed]
    report["reports"] = [item for item in report["reports"] if item["nodeid"] not in removed]
    with pytest.raises(ValueError, match="role/scenario"):
        checker().validate_report(report)


@pytest.mark.parametrize("identity", REQUIRED_PARAMETERS)
@pytest.mark.parametrize("layer", ["collection", "selection", "setup", "call", "teardown", "all", "junit"])
def test_each_required_parameter_cannot_be_omitted_from_evidence(tmp_path, identity, layer):
    from xml.etree import ElementTree

    report = good_report()
    role, scenario, parameter = identity
    check = {"role": role, "scenario": scenario, "parameter": parameter}
    item, = (n for n in report["collected"] if check in n.get("checks", []))
    node = item["nodeid"]
    root = ElementTree.Element("testsuite")
    for collected in report["collected"]:
        if layer in {"junit", "all"} and collected is item:
            continue
        ElementTree.SubElement(root, "testcase", classname=collected["junit"][0], name=collected["junit"][1])
    junit = tmp_path / "junit.xml"
    ElementTree.ElementTree(root).write(junit, encoding="utf-8")
    if layer in {"collection", "all"}:
        report["collected"] = [n for n in report["collected"] if n["nodeid"] != node]
    if layer in {"selection", "all"}:
        report["selected"].remove(node)
    if layer in {"setup", "call", "teardown", "all"}:
        report["reports"] = [r for r in report["reports"]
                             if r["nodeid"] != node or (layer != "all" and r["when"] != layer)]
    with pytest.raises(ValueError):
        gate = checker()
        gate.validate_report(report)
        gate.validate_junit(junit, report)


@pytest.mark.parametrize("tag", ["skipped", "failure", "error", "missing"])
def test_junit_cross_check_rejects_missing_or_unsuccessful_execution(tmp_path, tag):
    report = {"collected": [{"junit": ["tests.common.db.test_example", "test_mysql"]}]}
    case = "" if tag == "missing" else f'<testcase classname="tests.common.db.test_example" name="test_mysql"><{tag}/></testcase>'
    path = tmp_path / "junit.xml"
    path.write_text("<testsuite>" + case + "</testsuite>", encoding="utf-8")
    with pytest.raises(ValueError):
        checker().validate_junit(path, report)


@pytest.mark.parametrize("identity", API_HEALTH_PARAMETERS)
@pytest.mark.parametrize("mutation", ["missing_node", "missing_parameter"])
def test_api_health_partial_evidence_is_rejected(identity, mutation):
    report = good_report()
    role, scenario, parameter = identity
    expected = {"role": role, "scenario": scenario, "parameter": parameter}
    entry, = (n for n in report["collected"] if expected in n.get("checks", []))
    if mutation == "missing_node":
        node = entry["nodeid"]
        report["collected"].remove(entry)
        report["selected"].remove(node)
        report["reports"] = [r for r in report["reports"] if r["nodeid"] != node]
    else:
        entry["checks"].remove(expected)
    with pytest.raises(ValueError, match="role/scenario"):
        checker().validate_report(report)
