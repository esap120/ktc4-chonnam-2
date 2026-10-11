# JobExecution read port 연결 — `CaseStore`에 주입하고 case가 조회한다

> **상태: 결정 · 구현** · 결정일 2026-10-11 · 담당 유소연(`case`) · 근거 W7 고도화 8순위 8-10(`../design-refinement-w7-baseline.md`), #245 D-6 · #248 Q-1, Runtime RT-03 read port(`src/daesingo/common/jobs/read_port.py`), RT-08(#295) · RT-09(#296)
> case 진입 함수의 인자 모양과 CaseView 투영 방식이라 case 단독 결정 범위다. read port의 모양 · transaction 참여 방식은 Runtime 소유(Tech Spec §12)이고, 대표 execution 선택 규칙은 CaseView 계약 A§10-6 · §10-7이 소유한다. 이 문서는 case가 그 port를 어떻게 받아 쓰는지만 둔다.

## 배경

실행 상태(JobExecution)는 호출자가 미리 조회한 리스트를 `job_executions=` 인자로 넘겼다(`get_view` · `build_view_from_adapter` · `handle_command` · `execute_command`). 그런데 어떤 `job_id`를 조회할지는 case를 로드해야 안다. HTTP 쪽 호출자(RT-08 `/view` · `/commands`)는 이 리스트를 미리 만들 방법이 없다. Fine 실행 상태(`visual_verify_status`)도 「worker 경로에서는 `representative_execution_status(..., "FINE_VERIFY")`가 만든다」고만 적혀 있었고 실제로 만드는 곳이 없었다.

Runtime read port `read_executions(conn, job_ids)`는 RT-03으로 머지됐다. 요청한 job의 모든 attempt를 Contract 모양으로 돌려주고, 대표는 case가 고른다. 호출자 transaction에 참여하고 잠그지 않는다.

## 결정

1. **read port는 `CaseStore(executions=…)`로 주입한다.** case는 `ExecutionReader` Protocol(`(conn, job_ids) -> list[dict]`)만 정의하고 Runtime 구현을 import하지 않는다. composition root(api · worker)가 `CaseStore(repository=…, conn=…, executions=read_executions)`로 꽂는다. `CaseStore`가 이미 `conn`과 호출자 transaction을 묶고 있어 진입 함수 인자가 늘지 않는다.
2. **조회는 `CaseStore.read_executions(case)`가 한 번 한다.** 그 case의 `job_records` 전체 `job_id`를 같은 `conn`으로 넘긴다. job이 없거나 reader가 없으면 조회하지 않고 `[]`이다 — in-memory 테스트 · 데모는 「실행 기록 없음」으로 그대로 동작한다.
3. **진입 함수의 `job_executions=` · `visual_verify_status=` 인자를 없앤다**(`get_view` · `handle_command` · `execute_command`). `running_jobs=`를 없앤 것(`running-jobs-derivation.md` 결정 6)과 같은 이유다 — 호출자가 덮어쓸 길이 있으면 port 결과와 다른 값이 화면에 갈 수 있다. `build_view_from_adapter(case, adapter, executions=…)`는 조회 결과를 받는 조립 함수로 남고, 순수 조립 함수 `build_case_view(job_executions=…, visual_verify_status=…)`도 그대로다.
4. **같은 조회 결과로 case가 두 가지를 계산한다.**
   - `running_jobs` — `view.derive_running_jobs()`(변경 없음).
   - `visual_verify_status` — 가장 나중 `FINE_VERIFY` job의 attempt 최댓값(`view.representative_execution_status`, A§10-6 · §10-7). `search.visual_verify_failed` notice(8-14)가 실제 실행 상태를 따라간다.
5. **transaction.** `get_view`는 case를 `share`로 로드한 뒤, command는 같은 transaction 안에서 조회한다. read port는 잠그지 않으므로 「case 행 먼저」 잠금 순서(`case-store-mysql.md`)와 부딪히지 않는다. command 응답은 enqueue 전에 조립되므로 방금 append한 job은 여전히 `PENDING`이다(8-11).

## 알려진 한계

- **「가장 나중 `FINE_VERIFY` job」은 후보에 묶여 있지 않다.** A→B→A처럼 관찰을 재사용해 새 Fine을 발주하지 않으면(`reselect-observation-reuse.md`) 대표가 B의 Fine이다. 지금은 real 경로가 `FINE_VERIFY`를 발주하지 않고(데모만), notice가 `evidence=null`일 때만 붙어 드러나지 않는다. Fine을 Worker로 발주하는 배선(6.6순위 조건 2 · 8-9)에서 후보 context로 거른다.
- in-memory 경로의 `MockFixtureAdapter.get_job_executions()`는 fixture 대조 테스트용으로 남는다. 진입 함수는 이것을 읽지 않는다.

## 고르지 않은 안

| 안 | 고르지 않은 이유 |
| --- | --- |
| 진입 함수마다 `read_executions=` 인자 | `get_view` · `execute_command` · `handle_command` · `build_view_from_adapter`에 다 붙이고 `conn`도 따로 넘겨야 한다. `CaseStore`가 이미 요청 transaction 단위로 만들어진다 |
| `job_executions=` 인자를 남기고 없을 때만 port | 경로가 둘이 되고, 호출자 값이 port 결과를 덮어쓸 수 있다 |
| `visual_verify_status`는 호출자에게 계속 받기 | 호출자가 대표 job을 고르려면 case의 `job_records`를 알아야 한다 — case 내부 규칙(A§10-7)을 밖으로 낸다 |
| case가 `daesingo.common.jobs.read_port`를 직접 import | 모듈 경계(case는 Runtime 물리 구현을 모른다). composition root 주입이 Runtime 계획 「`GET /view` — read port 주입한 `get_view`」와 같다 |

## 테스트

- `tests/case/test_execution_read_port.py` — fake reader로 `get_view` · command 응답(성공 · 거부)의 `running_jobs`, 그 case의 job만 요청, job 없으면 호출 안 함, reader 없으면 `PENDING`.
- `tests/case/test_visual_verify_failed_notice.py` — Fine 상태를 조회 결과에서 고름, 다시 발주한 Fine이 진행 중이면 이전 실패로 notice를 붙이지 않음.
- `tests/case/test_execution_read_port_mysql.py`(MySQL opt-in, CI 필수) — case · runtime migration 위에서 Runtime `enqueue` → `PENDING`, `claim_one` → `RUNNING`, 같은 transaction의 미커밋 enqueue를 읽음.

## 남은 것

- RT-08(b)가 `CaseStore(executions=read_executions)`로 꽂는다(#295).
- `usage_refs`는 RT-07 전까지 `[]`이다 — case는 쓰지 않는다.
