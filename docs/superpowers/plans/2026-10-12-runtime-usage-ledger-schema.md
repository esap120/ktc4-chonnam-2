# RT-07(a) Usage ledger schema implementation plan

> **For agentic workers:** Execute inline with superpowers:executing-plans and TDD. The user explicitly authorizes continuing after a meaning-preserving recommendation and prohibits commits, staging, push and PR creation.

**Goal:** Add Runtime usage persistence and a caller-transaction Final append primitive, without implementing the sink or reconciliation.

**Architecture:** Frozen `runtime_0003` follows `runtime_0002`. Independent in-flight and Final tables share `usage_id` PK, without FKs. Final insertion compares an existing immutable snapshot on duplicate identity, never updates it. Amount bindings validate exact decimal representation before MySQL conversion.

**Tech Stack:** SQLAlchemy Core, Alembic, Decimal, real MySQL 8.4, pytest JSON/JUnit acceptance gates.

**Spec:** `docs/runtime/runtime-implementation-plan.md` §6 RT-07 / §12; `runtime-tech-spec.md` §3.3 / §4.5 / §11; UsageRecord Final Contract §4–8; #244 final decision; #294; Baseline B-G1 / §2.12. Supplied AGENTS.md applies; no repository AGENTS.md file was found.

## Global Constraints

- RT-07(a) only; sink/Worker injection, reconciliation/late observations/sweep, Search wiring, pricing/FX, retention/purge and budgets remain excluded.
- Contract, Accepted Decision and Baseline semantics stay unchanged. Stop if external semantics require an authority decision.
- Keep current `feature/runtime-usage-ledger-schema`; leave initial untracked files untouched. No staging, commit, push or PR. Link `Refs #294 (RT-07(a))`; RT-07 stays `IN_PROGRESS`.
- Required real MySQL evidence: skip=0, xfail=0, complete required parameters in both JSON/JUnit.

## Design choices and failure modes

| Choice | Alternatives and risk | Selected implementation detail |
| --- | --- | --- |
| DECIMAL | (20,6) requires rejecting or rounding fractions beyond six places; (38,18) limits unquantized producer values to 18 fractional places; (65,30) costs more storage | (65,30), 35 integer / 30 fractional digits, explicit rejection before binding; no rounding |
| Identity | Composite execution+usage uniqueness permits global ID reuse; surrogate PK alone permits duplicate Final | `usage_id` ascii_bin PK in both tables; execution_ref nullable/indexed |
| References | FK Final→in-flight couples durable ledger to tracking lifecycle; cascade risks deleting Final; no FK leaves internal reference responsibility | Shared ID without FK, independently stored Final Contract snapshot; no cross-module FKs |
| Replay | Fresh ID duplicates charges; upsert overwrites history; ignore hides mismatched snapshots | Fixed-ID INSERT; only duplicate-key error gets locked read and full typed comparison; identical=false/no-op, mismatch=explicit conflict |

**Amount rationale:** Search `ProviderUsage.cost_with_rates` uses Decimal(str(rate)), integer token multiplication and division by 1,000,000, without quantization; Contract examples include 184.20 and 0. No Accepted Decision fixes a future KRW output bound. 65/30 uses MySQL's supported maximum to avoid inventing a pricing rounding policy. It does not promise that arbitrary future producer values fit. Out-of-range or more than 30 declared fractional places (including trailing zeros) fail rather than being quantized. Negative finite amounts are not forbidden by an invented pricing policy.

MySQL references: [DECIMAL characteristics](https://dev.mysql.com/doc/refman/8.4/en/precision-math-decimal-characteristics.html), [rounding](https://dev.mysql.com/doc/refman/8.4/en/precision-math-rounding.html). Raw SQL bypasses the application binder and MySQL may round before evaluating CHECK; no claim is made that CHECK can detect the original raw precision.

**COMMIT unknown:** This primitive returns tentative transaction-local results. It creates no IDs, owns no transaction and invokes no provider. A caller retains the same identity and complete snapshot across retries. INSERT waits for a competing transaction; duplicate-key locked read verifies the committed snapshot, while a rolled-back first writer allows insertion. Recovery of other effects in the caller's transaction requires those effects to be independently replay-safe; this primitive does not prove an entire unrelated transaction committed.

**In-flight shape:** Typed invocation identity/context, observations, optional safe failure category, pending/durable run relationship, state STARTED/OBSERVED/FINALIZED and observation/finalization timestamps. Final has only Contract fields flattened to typed columns. Pending run relationship is allowed only in in-flight. No TTL or recovery eligibility policy is introduced.

## Review Focus

- Decimal context precision must not round validation/serialization at 65 digits.
- Nullable token/run CHECKs must reject SQL UNKNOWN loopholes and partial objects.
- Same identity with different amount/null, run, pricing or context must fail without changing Final.
- Competing insertion rollback and real COMMIT response loss must resolve by the fixed identity.
- Removing one required parameter while retaining its family must fail the JSON/JUnit gate.

## Tasks

### Task 1: Exact amount boundary

Files: `src/daesingo/common/usage/amount.py`, `tests/common/usage/test_amount.py`.

- [x] Write and run RED for `parse_amount(Decimal | str | None) -> Decimal | None`, `amount_string(...) -> str | None`: float/int/bool rejection, finite values, 35/30 boundary and overflow, null vs zero, small context precision.
- [x] Implement tuple/exponent validation without arithmetic/quantize; a SQLAlchemy Decimal type binds only the validated string.
- [x] Run GREEN.

### Task 2: Schema and Final append

Files: frozen `migrations/runtime/versions/0003_usage.py`; live `common/usage/schema.py`; `common/usage/repository.py`; `tests/common/usage/test_usage_repository_mysql.py`.

Interfaces: `append_final(conn, record: Mapping) -> bool` (inserted vs identical); `read_final(conn, usage_id) -> dict | None`; `UsageIdentityConflict`.

- [x] Write RED tests using real MySQL: upgrade from prior head with existing rows, schema/metadata equivalence, typed CHECK rejection, direct PK rejection, exact amount roundtrip, caller commit/rollback, full duplicate snapshot comparison, concurrency and actual COMMIT OK discard proxy.
- [x] Implement independent frozen migration and metadata, strict allowlist validation/projection, INSERT-only append/replay.
- [x] Run GREEN, update existing migration inventory/head expectations without weakening tests.

### Task 3: Gate and documentation

Files: `scripts/check_mysql_test_report.py`, `tests/common/db/test_mysql_gate.py`, `tests/common/db/integration/test_migration_gate.py`, common README, Implementation Log.

- [x] Write RED for absent usage family and each absent required parameter, including partial family evidence and JUnit omission.
- [x] Extend acceptance inventories and actual MySQL nested-run/mutation coverage.
- [x] Run entire pytest suite with real MySQL required, independently validate JSON/JUnit, boundary checker and diff check.
- [x] Preserve exact commands/results and Implementation Notes, prepare a review manifest/diff, leave uncommitted/unstaged. No remote CI or independent review claim without evidence.

Final evidence: Runtime Implementation Log RT-07 and `.codex-scratch/rt07a-20261012/implementation-notes.md`. Full run retained one existing API blocker-rollback connection failure; unchanged-source recheck passes 5,022 tests with 26 non-MySQL skips, excluding only the already-passing nested report mutation test. Actual nested suite and regression recheck each pass the 445-test MySQL gate with skip=0/xfail=0. All 2,093 real-report parameter mutations are rejected, including usage 80×7=560. Read-only reviewer confirmed the PAD SPACE correction with an independent SELECT probe and existing GREEN evidence; no reviewer pytest is claimed.
