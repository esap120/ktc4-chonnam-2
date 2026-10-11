# RT-02(a) DB foundation implementation plan

> Execution: inline, approved by the user. TDD for each behavior; no commits, pushes, PR creation, or worktree switch. The approved conversation design and Runtime Plan RT-02(a) are the specification.

**Goal:** Role-specific synchronous MySQL factories, caller-owned callback transactions, real MySQL integration harness, and fail-closed CI execution evidence.

**Architecture:** SQLAlchemy Core Connection callbacks; context managers own resource cleanup. Worker retries only the complete DB callback; API executes once and distinguishes pre-commit dependency failures from unknown commit outcomes. Test-only schemas and a COMMIT-response proxy exercise real MySQL.

**Tech stack:** Existing locked SQLAlchemy/PyMySQL/Alembic/pytest; standard library only for additional support.

## Constraints and review focus

- B-D8 max_attempts=3 includes the initial attempt, with at most two additional attempts and 1-second intervals. PM clarification: Issue #289 comment 6036679371.
- Preserve RT-01 DbSettings and service defaults, P-5 Connection participation, Case ownership and case-first lock ordering.
- No runtime tables, migration env/runner, startup migration, HTTP mapping, Case fixture edits, or Baseline/Contract changes.
- Preserve recording-baseline-negative-001.json and existing user files. Keep RT-02 IN_PROGRESS and Issue #289 open.
- Check hidden commit in callbacks, unknown commit replay safety, cleanup errors masking commit outcomes, URL options overriding role policies, and collection/xfail/deselection bypasses.

## Task 1: Factories

Files: common/db/engines.py and __init__.py; tests/common/db/test_engines.py.
Produces: create_api_engine(db), create_worker_engine(db), create_heartbeat_engine(db, heartbeat), create_ready_engine(db, ready), create_migration_engine(url, explicit timeout arguments).

- [x] RED: role policy and custom timeout forwarding; URL policy bypass rejection; no eager connect/migration.
- [x] GREEN: RC, physical-connect lock wait hook, application QueuePool, dedicated NullPool, separate migration policy.
- [x] Verify focused tests.

## Task 2: Transactions

Files: common/db/transactions.py and errors.py; tests/common/db/test_transactions.py.
Produces: run_worker_transaction(engine, operation, *, sleep, logger), run_api_transaction(engine, operation, *, logger); safe failure types.

- [x] RED: success, complete callback retry, max 3 attempts / 2 sleeps, nonretryable propagation, API once, commit phase, cleanup, callback-owned commit rejection.
- [x] GREEN: complete transaction cleanup before retry, driver disconnect classification, safe logging, no HTTP semantics or domain imports.
- [x] Verify focused suite.

## Task 3: Harness and CI gate

Files: root conftest.py, tests/mysql_harness.py, scripts/check_mysql_test_report.py, pyproject.toml, tests/common/db/test_mysql_gate.py.

- [x] RED: require mode cannot hide URL/dependency/connect/privilege errors; marker inference for unchanged Case tests; skip/xfail/deselection/empty or missing scenario reports fail.
- [x] GREEN: schema-per-test fixtures, early preflight, collected/run report; independent report checker.
- [x] Verify subprocess gate tests.

## Task 4: Real integration tests

Files: tests/common/db/integration and test-only support.

- [x] Tests for sessions/replacement/pool/heartbeat/ready, actual 1205/1213/KILL, rollback/read replay, API commit boundaries, real COMMIT-response loss, and Case repository compatibility. Absent proxy was RED; compatibility assertions reused already implemented factories and passed directly.
- [x] Keep every network/lock fault real; coordinate using events/barriers and bounded waits. MySQL 8.4.7 ran in isolated WSL scratch, independent of the user's existing MySQL 8.0.
- [x] Verify with DAESINGO_REQUIRE_MYSQL=1 against MySQL 8.4. No mock/skip substitution.

## Task 5: Workflow, docs, final verification

Files: existing python-tests.yml; Runtime Implementation Log; common/root README facts.

- [x] Add MySQL 8.4 service, test URL / require flag, full-suite report, no-skip/no-xfail and required-scenario check. Preserve protected workflows and lockfile. Remote Actions execution is pending; no push/PR authorized.
- [x] Record implementation choices, B-D8 counting, verification and limitations; RT-02 remains IN_PROGRESS. Future PR notes use Refs #289 (RT-02(a)); keep their content in the Implementation Log rather than a repository PR-body draft.
- [x] Run full pytest, real MySQL suite/report gate, boundary, Contract fixture and git diff --check. Review complete diff and report exact skips / remaining acceptance.

## Execution ledger

- Initial: branch feature/runtime-db-foundation, bcc0730; only pre-existing untracked recording-baseline-negative-001.json. Existing Python requires sandbox escalation for DLL loading; no installation performed.
- Ruling: work in the user's named feature branch and current checkout; preserve the approved execution scope instead of creating a second checkout or committing a plan.
- Initial verification (2026-10-07): 1935 passed / 26 unrelated opt-in skips; real MySQL 8.4.7 40 passed / skip=0 / xfail=0; report/JUnit gate, boundary, Contract fixture and diff checks PASS. Initial read-only reviewer findings were addressed; see the later independent-review findings below. Details and exact skips in Runtime Implementation Log RT-02.
- No project dependency install or lockfile change. MySQL binary and shared libraries were extracted into ignored scratch to run the real integration server; system packages and the user's MySQL service were unchanged. No commit/push/PR.
- 2026-10-08: independent review reproduced schema query overrides, cleanup masking COMMIT uncertainty, and missing role-specific gate requirements. Added RED regressions and minimal fixes; current evidence is in Implementation Log RT-02. Earlier PASS/review claims are historical, and the current revision awaits independent re-review. Existing scratch/user files are untouched; this run uses a separate OS temp directory.
- 2026-10-08 final verification: 2022 passed / 26 unrelated opt-in skips; real MySQL 8.4.7 46 passed / skip=0 / xfail=0, Case 18 preserved, 32 role/scenario combinations required. Actual-report mutation checks, actionlint/ShellCheck/YAML/bash syntax, boundary, Contract fixtures and tracked/new-file diff checks PASS. Current independent re-review and remote Actions execution remain pending; RT-02 stays IN_PROGRESS.
