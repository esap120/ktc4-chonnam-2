# RT-06(b) T2 redelivery and kill recovery

**Goal:** recover unapplied SUCCEEDED/FAILED executions using the existing T2 and Case 8-8 ports. Refs #293; RT-06 remains IN_PROGRESS until final independent review.

**Architecture:** nonlocking candidate scan, connection returned, one B-D8 transaction per candidate. Re-read the receipt without a Runtime lock, then let Case acquire its lock before Runtime receipt/enqueue writes. Case execution identity and the atomic Runtime receipt resolve concurrency and unknown COMMIT. Worker composition owns the Case adapter and injected reader/timeline/store factory.

**Spec:** runtime-implementation-plan §6 RT-06 / §12, runtime-tech-spec §6.2/6.3/7.2/7.3/12.2, provisional-baseline-v0.1 B-L3–5/B-R1–3/§2.4/3.2/9, Case result-reflection decision, Issue #293 and merged PRs #342/#343. Supplied AGENTS.md applies; no repository AGENTS.md was found.

## Choices

| Concern | Selected | Alternatives / failure without selected guarantee |
| --- | --- | --- |
| scan | unlocked candidates + short per-candidate transactions | whole-pass transaction couples failures/locks; Runtime-first locking violates Case-first order |
| concurrency | existing Case lock + execution dedup + Runtime receipt recheck | process mutex cannot protect other processes; delivery lease introduces another recovery policy |
| unknown COMMIT | existing B-D8 replay with durable receipt | assume rollback loses committed effects; unconditional enqueue duplicates jobs |
| adapter | worker adapter with injected ProducedReader, timelines and optional store factory | common→Case imports violate boundaries; Case Runtime types change another Owner surface |
| kill synchronization | IPC barrier, independent durable DB reads, kill/join | sleep alone cannot prove kill position; mocked death cannot prove lease recovery |
| unsupported kind | preserve Case ValueError, no receipt, isolate candidate | silent APPLIED loses results; kind filtering hides wiring faults |

## Execution (inline, no commit/push/PR)

- [x] RED: candidate eligibility, faults, receipt/concurrency, startup ordering, Case atomicity and kill tests; gate family omissions. Parameter omission GREEN is in the gate regression.
- [x] Implement common/jobs/redelivery.py, worker/case_reflector.py, SweepService/composition wiring.
- [x] Targeted unit/integration GREEN, including commit response proxy and concurrent Case locks. Read-only review P2 fixture corrected via durable-kind RED→GREEN; actual DB connection kill isolation verified.
- [x] Real MySQL require inventory: full 487 / nested 482, skip 0, xfail 0, JSON/JUnit gates; 2,317 evidence-layer omissions rejected, including new 224, plus 9 new family omissions.
- [x] Full pytest: 5,363 passed / 26 non-MySQL skips. Boundary checker, Contract fixtures, all workflow static checks and git diff --check PASS.
- [x] Implementation Log/README, read-only source review and residual risks; dedicated server/schema/account/process cleanup verified. Final independent re-review and Owner audit remain pending; RT-06 IN_PROGRESS. RT-07 reconciliation and Case capability extensions remain out of scope.

## Review focus

- CANCELLED/STALE and existing receipts never enter redelivery.
- Candidate and replay reads never lock Runtime before Case; post-Case receipt prevents duplicate enqueue.
- Reflector, DB and logger errors leave no partial T2 and do not stop other candidates/cycles.
- Real process death is observed and cleanup precedes dropping its schema; retries use DB lease/backoff time.
- KindRegistry can produce FAILED/RUNTIME_UNREGISTERED_KIND and deliver T2: RT-10 must own handler/reflection compatibility fail-fast, with no invented Case applier here.
