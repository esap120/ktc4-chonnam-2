# RT-07(b) UsageSink and explicit finalize Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in the current branch. User explicitly requires no commit, push or PR; preserve all pre-existing untracked files.

**Goal:** Persist each invocation's STARTED and OBSERVED facts, then atomically append one Final after the caller confirms its logical Run relationship.

**Architecture:** A stdlib-only UsageSink Protocol lives in common/usage/port.py. An execution-scoped durable implementation receives a DB-only transaction runner from Worker composition. Each method closes its transaction before returning; provider I/O is entirely caller-owned.

**Tech Stack:** Existing Python, SQLAlchemy Core, MySQL 8.4, pytest and runtime_0003.

**Spec:** runtime-tech-spec.md §3.3/4.5/11, contract-usage-record.md §4–8, Accepted #244 final comment 5979576799, implementation-plan.md §6 RT-07/§12. PR #349 merged as fa5a0fcbd5f88e70e7a4c9ba0a457b42a65a27a1; current HEAD 51683e0b.

## Global constraints

- No Search/provider modifications, recovery, sweep registration, late-observation policy, usage_refs projection, pricing/FX, retention or budget changes.
- Preserve append_final, DECIMAL(65,30), frozen migration and DB CHECK semantics.
- Runtime supplies identity/execution/case; caller supplies observed facts and confirmed Run relationship, including actual FAILED Runs.
- Unknown amount remains null. No HTTP in a retry callback. No fencing away already observed usage after ownership loss.
- RT-07 remains IN_PROGRESS; Refs #294 (RT-07(b)); PR and merge SHA pending.

## Choices and failure modes

| Choice | Alternatives | Selected / failure prevented |
| --- | --- | --- |
| persistence | engine inside sink / transaction runner injection | runner injection; isolates DB policy and keeps Protocol dependency-free |
| identity | fresh per retry / fixed before callback | fixed ID and typed snapshot; avoids duplicate STARTED after unknown COMMIT |
| state transition | unconditional upsert / locking read + conditional UPDATE | locking read and expected-state predicate; prevents overwriting observed facts |
| concurrent snapshot | last writer wins / compare and conflict | same data no-op, different data conflict; serialization through tracker lock |
| Final ordering | separate transactions / append then marker in same transaction | append_final then FINALIZED; both roll back on marker failure |
| injection | shared sink / per-claim factory | per-execution factory before dispatch; no shared tracker cache |
| errors | provider-shaped errors / sanitized UsageError hierarchy | explicit persistence, validation, identity/state errors; Worker FAILED without HTTP redispatch |

## Review focus

- begin COMMIT unknown and retry exhaustion: retain Runtime-issued identity on sanitized persistence error for explicit begin replay; caller must never interpret replay as authorization to repeat an already sent HTTP.
- mutable input: normalize to typed private snapshots before entering transaction callback.
- finish/finalize races: Final is only legal from OBSERVED; identical finish remains no-op after normal finalization; conflicting observation never overwrites.
- ownership loss: finish/finalize do not use ownership admission guards; recovery handling is deferred.
- exception privacy: no raw input/SQL/driver error in UsageError text, cause, structured log or Pydantic ValidationError.

## Task 1: durable port and tracker

Files: common/usage/{port,sink}.py; tests/common/usage/test_usage_sink{,_mysql}.py.

Interfaces: begin(operation, provider_label, pricing_context, *, usage_id=None) -> str; finish(usage_id, *, token_usage, processed_duration_sec, latency_ms, pricing_context, cost, outcome, failure_kind=None) -> None; finalize(usage_id, *, run_ref, run_ref_reason) -> None. begin replay uses only a previously Runtime-issued identity held by this execution's sink; no recovery lookup surface is introduced.

- [x] Write RED unit tests for frozen identity/snapshot, failed begin HTTP=0, failed finish HTTP total=1, validation privacy and Protocol typing.
- [x] Run targeted pytest and retain RED output.
- [x] Implement typed normalization, sanitized errors and DB-only callbacks. begin compares immutable STARTED context even after later states. finish compares all observation fields. finalize builds Contract projection from locked tracker and appends before marking FINALIZED.
- [x] Add real MySQL RED/then GREEN tests for N invocations, replay/conflicts, missing/start-only identity, concurrent finish/finalize, rollback at both Final/marker boundaries, 1205/1213 and actual proxy COMMIT ACK loss for each method.

## Task 2: Worker execution isolation

Files: common/jobs/{execution,worker_loop}.py, worker/composition.py; tests/worker/test_usage_worker_mysql.py.

- [x] Write RED tests for factory per execution, pre-dispatch cancellation usage=0, usage persistence terminal error and two execution isolation.
- [x] Type ExecutionContext.usage_sink as UsageSink | None; create a fresh sink via injected WorkerLoop factory for each claim. Production composition binds run_worker_transaction without ownership guards to usage persistence.
- [x] Validate Runtime usage errors become RUNTIME_USAGE_* FAILED; record retries reuse terminal facts and never redispatch HTTP.
- [x] Run worker unit and actual MySQL tests.

## Task 3: fail-closed gate and review evidence

Files: tests/usage_acceptance.py, scripts/check_mysql_test_report.py; existing gate tests automatically consume independent acceptance inventory; Runtime Log and READMEs.

- [x] Add independent usage_sink acceptance families/parameters; confirm gate tests RED before adding production requirements.
- [x] Add identical mandatory inventory to production gate; run pure gate and actual JSON/JUnit parameter-removal checks (collection/selection/phases/JUnit).
- [x] Run require-MySQL suite (skip/xfail=0), full pytest, boundary, Contract fixtures, workflow static checks and git diff --check.
- [x] Review diff; update RT-07 Log with implementation differences, choices, exact direct verification and remaining risks. Clean this run's schemas/accounts/connections/server, preserve evidence under .codex-scratch.
- [x] Stop with local reviewable changes; no staging/commit/push/PR.
