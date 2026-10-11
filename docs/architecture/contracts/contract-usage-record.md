# Data Contract — UsageRecord v1

**Status:** `Final — Accepted`

**Accepted:** `2026-09-05` (v1) · `2026-09-07` (v1.1 — B05 종결) · `2026-09-10` (v1.2)

**수락 근거:** PM의 common/runtime Owner 결정이다. 기존 근거와 PM 추가 결정은 §9에서 구분한다. **v1.1의 `run_ref` 변경은 신유민(`readout`)과 공동 결정, 김대원(`eval`) 확인 — `UsageRecord`에 대한 첫 문서화된 소비자 확인이다**(§9-5). **v1.2는 이슈 #33 Required-5/Required-7·A-1·A-6에 대한 case(유소연) 통합 초안이었다.** 원래 이 초안의 PR 리뷰 확인은 김준영(evidence/common-runtime) PR #8에서 받기로 했으나, **PR #8이 그 이전 롤백 전 내용으로 작성돼 폐기됨에 따라(2026-09-10)**, §5 `run_ref` 필드 설명이 §7-1의 `run_ref_reason` 예시와 어긋나 있던 것(이슈 #30 B-1, 김대원 eval 3차 검수가 지적)을 포함해 case가 직접 마무리했다. 김준영의 사후 확인은 여전히 유효하다.
**Architecture Contract:** v4 §5-1 ⑫ · §4-모듈2 ⑥ · §4-모듈7 ⑤
**Contract Version:** `usage-record/v1.2`
**Producer / Owner:** `common/runtime` — 김준영
**Consumers:** `case` — 유소연 (예산 소진) · `eval` — 김대원 (비용 분모 집계) · `search` — 서어진 (`AnalysisRun.usage_refs[]` 생성 시점 연결) · `readout` — 신유민 (`ReadoutRun.usage_refs[]` 생성 시점 연결, 2026-09-07 추가)
**Related ADR:** `adr/adr-usage-record.md` · 작성 경위 `adr/adr-consistency-2026-09.md` C1-8 · v1.1 근거 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.4

> **`usage-record/v1.2` (2026-09-10, 이슈 #33 A-1/A-6 · Required-5/Required-7 반영).** ① **row 생성 규칙을 명확히 좁힌다**(§9-6) — "실패/STALE attempt도 발행한다"는 mock pack v3 컨벤션(`docs/modules/case/decisions/eval-round2-ground-truth-and-usage.md` B-4)을 이 계약 본문으로 정식 흡수하되, 조건을 **"attempt마다 무조건"이 아니라 "실제 capability/provider invocation이 시작됐을 때(결과와 무관하게)"로 좁힌다.** queue에만 있다가 dispatch 전에 취소/실패한 attempt는 row를 만들지 않는다. ② `case_id`와 `run_ref`의 관계를 분리해 명시한다(§9-2 보강) — `case_id`는 사건 단위 집계 키, `run_ref`는 logical run 연결이며 **둘은 독립이다**(`case_id`가 있어도 `run_ref`가 없을 수 있고 그 반대도 가능). ③ `run_ref=null`인 row에 **`run_ref_reason`**을 추가한다 — `null`이 "Run 개념이 없는 직접 호출"인지 "Run은 있어야 하는데 아직 만들어지지 않았다(예: 실패로 Run 자체가 생성되지 못함)"인지를 구분한다. §10 불변조건 13~14 추가.

> **이 문서가 왜 지금 생겼나.** v4 §5-1 ⑫에 있고 `AnalysisRun` 계약이 `usage_refs[]`로 참조하며 「상세 usage ledger의 authoritative source는 `UsageRecord`」라고 못박았는데(계약 L36·L327), 그 정의가 어디에도 없었다. PM이 v4·AnalysisRun의 기존 결정과 추가 원장 설계를 모아 작성했다. 새로 정한 것은 §9, 정하지 않은 것은 §10이다.

---

## 1. 계약 목적

외부 유료 호출 **1건**의 사용량과 그 시점의 가격 맥락을 기록한다. 「이 사건 처리에 얼마 들었나」와 「지난달 실행을 지금 다시 계산하면 얼마인가」를 **둘 다** 답할 수 있어야 한다.

v4 §4-모듈2 ⑥은 정규화 사용량·가격 맥락의 상위 요구다. 구체 원장 설계에는 PM 추가 결정도 있다(§9).

> `AnalysisRun`은 과거 실행을 나중에도 비교할 수 있도록 **정규화된 사용량 + 실행 당시 pricing context를 추적할 수 있어야 한다.**

## 2. Producer / Consumer

**Producer**: `common/runtime` (김준영). 외부 호출을 실제로 수행하는 계층이 호출 1건당 1 row를 append한다. **(2026-10-04 표기 정합, 버전 유지, [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) RD-18)** provider 호출은 Search adapter가 수행하고 시도마다 Runtime usage tracker에 시작 · 완료 관측을 넘기며, Final row append는 common/runtime이 logical Run 연결이 확정된 뒤 호출 1건당 정확히 1번 한다. 필드 · 불변조건은 바뀌지 않는다. in-flight 추적 · 복구 방식은 Contract 밖 Runtime 구현이다([`runtime-tech-spec.md`](../../runtime/runtime-tech-spec.md) §11.1).

**Consumer**

| 소비자 | 무엇을 읽는가 |
| --- | --- |
| `case` | 예산 소진 판정. `AnalysisScope.budget.max_cost_krw`와 비교한다 |
| `eval` | 비용 분모 집계 (`cost_per_source_video_hour` · `cost_per_clip`) |
| `search` | 자기 Run에 속한 usage의 id를 `AnalysisRun.usage_refs[]`에 넣는다. **집계·판정은 하지 않는다** |
| `web` | 직접 읽지 않는다 |

## 3. 책임 경계

### 이 계약이 소유하는 것

- 외부 호출 1건의 정규화된 사용량
- 호출 시점의 가격 맥락(pricing context)
- 그 시점 계산된 금액
- 호출이 어느 Job 실행·어느 Run에 속하는지의 연결

### 이 계약이 소유하지 않는 것

- **예산 초과 여부의 판정** — `case`
- 평가 지표의 분모 선택 — `eval` (v4 §4-모듈7 ⑤)
- raw provider payload — **보존하지 않는다.** sensitive data 가능성이 있어 장기 보존·로그 정책과 분리한다(v4 §4-모듈2 ⑥)
- 사용자 식별 정보 — 어떤 형태로도 넣지 않는다

## 4. 확정 Contract 스키마 (JSON)

```json
{
  "usage_id": "string",
  "execution_ref": "string | null",
  "run_ref": { "kind": "analysis_run | readout_run", "ref": "string" },
  "run_ref_reason": "DIRECT_NO_RUN | RUN_NOT_PRODUCED | null",
  "case_id": "string | null",
  "occurred_at": "ISO8601",
  "provider_label": "string",
  "operation": "string",
  "token_usage": {
    "input_tokens": "int",
    "output_tokens": "int",
    "total_tokens": "int"
  },
  "processed_duration_sec": "number | null",
  "latency_ms": "int | null",
  "pricing_context": {
    "pricing_id": "string",
    "unit": "string"
  },
  "cost": {
    "amount": "decimal string | null",
    "currency": "string"
  }
}
```

## 5. 필드 정의

| 필드 | 타입 | 필수 | 의미 | 근거 |
| --- | --- | --- | --- | --- |
| `usage_id` | string | Y | 고유 식별자. `AnalysisRun.usage_refs[]`가 이 값을 담는다 | `AnalysisRun` 계약 L119 |
| `execution_ref` | string \| null | Y(키) | 이 호출이 속한 `JobExecution.execution_id` | §9-1 |
| `run_ref` | ContractRef \| null | Y(키) | 이 호출이 속한 logical run. 모양은 `contract-observation.md` §3의 `ContractRef {kind, ref}`(`JobExecution.produced`와 같은 참조 방식). **`kind`는 `analysis_run`(→`AnalysisRun.run_id`) · `readout_run`(→`ReadoutRun.run_id`) 두 값으로 닫는다** — 전역 `ContractRef.kind` 어휘를 닫는 것이 아니라 run identity를 뜻하는 kind가 이 둘이라는 필드 수준 제약이며 새 run 종류는 계약 개정으로만 추가한다. **null은 두 경우 중 하나다(v1.2 정정) — ① Run 개념이 없는 직접 호출, ② logical run을 시도했지만 산출물이 만들어지지 못한 채 종료된 호출(예: STALE로 끝난 attempt).** 어느 쪽인지는 옆 `run_ref_reason`이 구분한다(`DIRECT_NO_RUN` \| `RUN_NOT_PRODUCED`) — "Run 개념이 없을 때만 null"이라는 이전 문구는 실패/STALE row가 실제로 생기면서 `run_ref_reason` 없이는 두 경우를 구분할 수 없다는 게 드러나 폐기한다. Run에 속한 호출을 이유 없이 null로 기록하지 않는다 | B05 종결 (2026-09-07) · **정정(v1.2, 2026-09-10, 이슈 #30 B-1 · 김대원 eval 3차 검수) — `run_ref_reason`과의 불일치 해소, PR #8(김준영 초안)이 롤백으로 폐기돼 case가 직접 반영** · `AnalysisRun` 계약 L119 |
| `run_ref_reason` | `DIRECT_NO_RUN \| RUN_NOT_PRODUCED` \| null | Y(키, v1.2) | `run_ref=null`인 이유. `run_ref`가 존재하면 반드시 `null` | §9-6 |
| `case_id` | string \| null | Y(키) | 사건 단위 원가 집계용. eval fixture 호출이면 null. **`run_ref`와 독립이다**(v1.2) — 이 호출이 어느 case에 청구되는지와 어느 logical run에 속하는지는 서로 다른 축이다 | §9-2 |
| `occurred_at` | ISO8601 | Y | 호출 시각 | — |
| `provider_label` | string | Y | 과금 주체를 식별하는 라벨 | §9-3 |
| `operation` | string | Y | 호출 종류 (모듈 접두어 규칙) | §9-3 |
| `token_usage` | object \| null | Y(키) | `input_tokens`/`output_tokens`/`total_tokens`. provider가 token을 제공하지 않으면 **객체 전체를 null** | `AnalysisRun` 계약 L187 동일 형태 |
| `processed_duration_sec` | number \| null | Y(키) | 이 호출이 실제로 처리한 영상 길이. 없으면 null | v4 §4-모듈7 ⑤ |
| `latency_ms` | int \| null | Y(키) | 호출 왕복 시간 | §9-4 |
| `pricing_context` | object | Y | 실행 당시 가격 맥락 | v4 §4-모듈2 ⑥ |
| `cost` | Money | Y(키) | 실행 시점에 계산된 금액. 계산 불가면 `amount=null` | `AnalysisRun` 계약 L189 동일 형태 |

### `pricing_context`

| 필드 | 의미 |
| --- | --- |
| `pricing_id` | 이 호출에 적용된 가격표의 식별자. 가격표가 바뀌면 새 `pricing_id`가 생긴다 |
| `unit` | 과금 단위 (`per_1k_tokens` · `per_second` 등) |

**가격표 자체는 이 계약에 넣지 않는다.** row에 단가를 복제하면 가격표 개정 때 원천이 둘이 된다. `pricing_id`로 「어떤 가격표를 봤는지」만 남긴다. ~~표는 `common/runtime` config가 소유한다.~~ **(2026-10-02 · 표기 정합, 버전 유지)** 가격표 숫자의 위치는 이 계약이 정하지 않는다. 현재 MVP에서는 `search`가 rate를 주입받아 cost를 계산하고, 공용 versioned pricing catalog는 가격표를 직접 소비하는 요구가 실제로 여럿 생기면 다시 검토한다. `common/runtime`은 실행 시 전달받은 `pricing_context`와 `cost` snapshot을 그대로 보존한다. 근거: [Issue #153](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/153) 2026-09-26 Search·common/runtime Owner 코멘트 합의.

## 6. 정상 예시

```json
{
  "usage_id": "usage_101",
  "execution_ref": "exec_9001",
  "run_ref": { "kind": "analysis_run", "ref": "run_2026_0901_0007" },
  "run_ref_reason": null,
  "case_id": "case_3",
  "occurred_at": "2026-09-01T18:00:12Z",
  "provider_label": "gemini",
  "operation": "SEARCH_COARSE",
  "token_usage": { "input_tokens": 128400, "output_tokens": 2100, "total_tokens": 130500 },
  "processed_duration_sec": 3600,
  "latency_ms": 41200,
  "pricing_context": { "pricing_id": "gemini-2026-08", "unit": "per_1k_tokens" },
  "cost": { "amount": "184.20", "currency": "KRW" }
}
```

## 7. token을 제공하지 않는 provider 예시 — readout 실행에 속한 호출

```json
{
  "usage_id": "usage_205",
  "execution_ref": "exec_9010",
  "run_ref": { "kind": "readout_run", "ref": "rr_001" },
  "run_ref_reason": null,
  "case_id": "case_3",
  "occurred_at": "2026-09-01T18:11:02Z",
  "provider_label": "ocr-local",
  "operation": "READOUT_PLATE",
  "token_usage": null,
  "processed_duration_sec": 4.5,
  "latency_ms": 830,
  "pricing_context": { "pricing_id": "local-2026-09", "unit": "per_second" },
  "cost": { "amount": "0", "currency": "KRW" }
}
```

`token_usage`를 `0`으로 채우지 않고 null로 둔다. 0은 「호출했는데 토큰을 안 썼다」는 뜻이고 null은 「토큰이라는 개념이 없다」는 뜻이다(`Observation` 계약의 known-empty vs UNKNOWN 구분과 같은 원칙).

`run_ref`도 같은 원칙이다. 이 호출은 `ReadoutRun rr_001`에 속하므로 `{kind:"readout_run"}`을 채운다. **v1의 이 예시는 `run_ref: null`이었고 그것이 B05 지적의 실제 대상이었다** — `null`은 Run에 속하는데 연결을 못 적은 경우를 뜻하지 않는다. (v1 당시엔 `null`이 「Run 개념이 없는 직접 호출」만을 뜻한다고 썼으나, **v1.2에서 정정** — Run이 있어야 할 자리인데 산출물이 만들어지지 못해 끝난 호출도 `null`일 수 있다. 이 두 `null` 사유의 구분은 §7-1·§9-6의 `run_ref_reason`이 맡는다.) `execution_ref`와 `run_ref`는 둘 다 채운다 — 전자는 실행 1회분의 총 비용(§9-1), 후자는 어느 logical run에 속하는가다. `attempt`가 2 이상일 때 논리적 run을 어떻게 두는지는 `readout` 소유 판단이다.

## 7-1. `run_ref=null` 두 사례 — `run_ref_reason` (v1.2)

```json
{
  "usage_id": "usage_x001_plate_a1",
  "execution_ref": "exec_x001_plate_a1",
  "run_ref": null,
  "run_ref_reason": "RUN_NOT_PRODUCED",
  "case_id": "case_x001",
  "occurred_at": "2026-09-01T18:20:40Z",
  "provider_label": "ocr-local",
  "operation": "READOUT_PLATE",
  "token_usage": null,
  "processed_duration_sec": 2.1,
  "latency_ms": 900,
  "pricing_context": { "pricing_id": "local-2026-09", "unit": "per_second" },
  "cost": { "amount": "0", "currency": "KRW" }
}
```

이 호출은 실제로 provider invocation이 시작됐고(§9-6) STALE로 끝났다 — `JobExecution.status=STALE`이라 `ReadoutRun`이 만들어지지 못했다. **Run이 있어야 할 자리인데 실패로 못 만들어진 경우**라 `run_ref_reason=RUN_NOT_PRODUCED`다.

```json
{
  "usage_id": "usage_h001_report_video",
  "execution_ref": "exec_h001_report_video",
  "run_ref": null,
  "run_ref_reason": "DIRECT_NO_RUN",
  "case_id": "case_h001",
  "occurred_at": "2026-09-01T19:02:11Z",
  "provider_label": "internal-render",
  "operation": "PACKAGE_EXPORT",
  "token_usage": null,
  "processed_duration_sec": 6.0,
  "latency_ms": 5200,
  "pricing_context": { "pricing_id": "internal-2026-09", "unit": "per_second" },
  "cost": { "amount": "0", "currency": "KRW" }
}
```

이 호출(신고영상 export)은 애초에 `AnalysisRun`/`ReadoutRun` 어느 쪽 개념도 없는 직접 호출이라 `run_ref_reason=DIRECT_NO_RUN`이다.

## 8. 불변조건

1. `usage_id`는 재사용되지 않는다. row는 **append-only**다 — 수정·삭제하지 않는다.
2. **과거 가격 변경 때문에 `cost`를 다시 계산해 덮어쓰지 않는다** (`AnalysisRun` 계약 L193과 동일 원칙). 재계산이 필요하면 `pricing_context`로 별도 조회한다.
3. `token_usage`는 객체 전체가 null이거나 세 필드가 모두 존재한다. 일부만 채우지 않는다.
4. `total_tokens`는 `input_tokens + output_tokens`와 일치한다.
5. raw provider request/response payload를 저장하지 않는다 (v4 §4-모듈2 ⑥).
6. 사용자 이름·연락처·번호판 문자열·GPS 좌표를 넣지 않는다 (`product-spec.md` §7 · v4 §4-모듈2 ⑦).
7. `AnalysisRun.usage_refs[]`가 이 row를 가리키면, `AnalysisRun.usage_summary`는 해당 Run에 속한 row들의 **실행 시점 aggregate와 정합해야 한다** (`AnalysisRun` 계약 L194).
8. `search`는 `eval`의 존재를 모른다 — eval 전용 필드를 두지 않는다 (v4 §4-모듈7 ⑥).
9. (v1.1) `run_ref`는 `{kind, ref}`이며 `kind ∈ {analysis_run, readout_run}`이다.
10. (v1.1) Run에 속한 호출을 이유 없이 `run_ref=null`로 기록하지 않는다. ~~`null`은 Run 개념이 없는 직접 호출만을 뜻한다.~~ **(v1.2 정정, 이슈 #39 Required-4)** — Run이 있어야 할 자리인데 산출물이 만들어지지 못해 끝난 호출(예: STALE)도 `null`일 수 있다. 두 사유의 구분은 13번의 `run_ref_reason`이 맡는다.
11. (v1.1) `ReadoutRun.usage_refs`와 `UsageRecord.run_ref`가 어긋나면 **`UsageRecord.run_ref`가 기준**이다. 양방향 정합을 불변조건으로 강제하지 않는다 — 강제하면 어긋난 순간 판정 주체를 다시 정해야 하고 그 판정이 `eval`의 비용 숫자에 들어간다.
12. (2026-09-08 · 표기 정합, 버전 유지) `AnalysisRun.usage_refs[]`도 같은 지위다 — 조회 편의용 파생값이며 `UsageRecord.run_ref`와 어긋나면 **`UsageRecord.run_ref`가 기준**이다. 7번의 「해당 Run에 속한 row」는 `run_ref={kind:"analysis_run", ref:<run_id>}`인 row를 뜻한다. search Owner(서어진) 결정, eval(김대원) 확인. `adr/adr-data-contract-call-closure-2026-09-08.md` §4.2.
13. (v1.2) `run_ref != null ⇒ run_ref_reason = null`. `run_ref == null ⇒ run_ref_reason ∈ {DIRECT_NO_RUN, RUN_NOT_PRODUCED}`.
14. (v1.2) row는 실제 capability/provider invocation이 시작된 호출에만 생성한다(결과가 성공/실패/STALE 무엇이든 상관없다). queue 대기 중 dispatch 전에 취소된 attempt는 row를 만들지 않는다.

## 9. PM이 새로 정한 것 (소비자 통보 대상)

아래 네 행은 추가 필드 목록의 일부다. 호출 1건당 row, run_ref 대상 제한, token 합계·객체 단위 null, pricing_id를 통한 별도 가격표 관리, append-only 원장 및 raw payload 제외의 구체 규칙도 §3~§8에서 정했다. **§9만 보거나 모든 값이 상위 문서에서 유일하게 도출됐다고 가정하지 않는다.** 소비자 확인 범위는 §3~§10 전체다. **9-5의 `run_ref` 변경은 `readout`(신유민)·`eval`(김대원) 확인을 받았다** — 이 계약에 대한 첫 문서화된 소비자 확인이며 W04 잔여 중 `UsageRecord` 부분은 이것으로 종결된다. 나머지 행에 대한 `case`·`search` 확인과 §8의 삭제 금지 ↔ §10의 purge_case·보관 정책 관계는 확인 대기다.

| # | 항목 | PM 결정 | 왜 |
| --- | --- | --- | --- |
| 9-1 | `execution_ref` | `JobExecution.execution_id`를 참조 | `JobExecution.usage_refs[]`와 양방향이 된다. 실행 1회분의 총 비용을 세려면 필요하다 |
| 9-2 | `case_id`를 직접 둔다 | Run/Execution을 거치지 않고 사건 단위 원가를 바로 집계할 수 있게 | v4 §4-모듈7 ⑤의 `cost_per_source_video_hour`는 사건 단위 집계다. 매번 join하면 eval 쪽 부담이 커진다. eval fixture 호출은 `case_id=null` |
| 9-3 | `provider_label` · `operation` | 둘 다 opaque 라벨. `provider_label`은 과금 주체, `operation`은 모듈 접두어 규칙 | 비용 원장은 「어디에 돈을 냈는가」를 알아야 감사가 된다. **`Observation.source.kind`에 provider/model을 넣지 않는 규칙과 충돌하지 않는다** — 그 규칙은 관찰의 출처 표기에 대한 것이고, 비용 장부는 별개 값 공간이다 |
| 9-4 | `latency_ms` | 호출 왕복 시간을 usage row에 둔다 | v4 §4-모듈7 ⑤의 `latency_per_source_video_hour`가 이 값 없이는 안 나온다. `JobExecution`의 시각 3개는 Job 단위라 호출 단위 latency를 못 준다 |
| 9-5 | `run_ref`를 `ContractRef \| null`로 (**타입 변경 · v1.1 · 소비자 확인 완료**) | `kind ∈ {analysis_run, readout_run}`. 원장이 authoritative, `ReadoutRun.usage_refs`는 파생값. ~~`null`은 Run 없는 직접 호출만~~ **(v1.2 정정)** — `null`은 「Run 개념이 없는 직접 호출」과 「Run을 시도했지만 산출물이 못 만들어진 호출」 두 경우이며 `run_ref_reason`(§7-1·§8-13)이 구분한다 | 김준영·신유민 공동 결정, 김대원 확인(2026-09-07). 「비용 집계가 *어느 참조를 신뢰했는가*에 따라 달라지는 건 피해야 한다」(김대원)가 한쪽만 authoritative로 둔 근거다. 기각: `readout_run_ref` 별도 필드(run 종류마다 필드·분기 증가) · `ReadoutRun.usage_refs` 단방향만(원장 한 번 스캔 집계가 갈라짐). 근거 `adr/adr-data-contract-call-closure-2026-09-07.md` §4.4 |
| 9-6 | row 생성 조건 (**v1.2**) | "실패/STALE attempt도 row를 만든다"를 **"실제 capability/provider invocation이 시작됐을 때"로 조건을 좁혀** 명문화 | mock pack v3가 fixture 컨벤션으로 먼저 정했던 "모든 attempt가 row를 만든다"는 표현은 dispatch 전에 취소된 attempt까지 포함하는 것으로 오독될 수 있었다(이슈 #22 B-4 제기, 김대원). 실제로 비용/latency가 발생하는 것은 invocation이 시작된 순간부터이므로 그 기준으로 좁힌다 — eval의 비용 분모가 실제로 일어나지 않은 호출까지 세지 않게 하기 위함(이슈 #33 A-1). |

## 10. 미결 — 이 계약에서 확정하지 않는다

- ~~**B05 — ReadoutRun 연결**~~ → **종결 (2026-09-07, §9-5).** `AnalysisRun.usage_refs[]`의 「조회 편의 파생값」 표기도 **종결 (2026-09-08, search Owner 서어진 · eval 김대원 확인, §8-12).** 두 Run 계약의 `usage_refs`는 같은 지위이고 원장 `run_ref`가 유일한 집계 기준이다. `run_ref=null`의 의미는 (§8-10이 v1.1 당시 서술했던 「Run 개념이 없는 직접 호출만」에서) **v1.2(§7-1·§8-13, 이슈 #33 A-1/Required-5)로 두 사유로 넓어졌다** — 「Run 개념이 없는 직접 호출」과 「Run을 시도했으나 산출물이 못 만들어진 호출」이며 `run_ref_reason`이 구분한다. 「아직 정식 연결 방식이 없는 호출」이라는 세 번째 의미로는 넓히지 않았다 — 그런 호출이 실제로 있다면 이 계약 Owner가 별도로 판단한다.

- ~~**통화를 KRW로 고정할 것인가.** `AnalysisScope.budget.max_cost_krw`는 KRW를 전제하고 `AnalysisRun.usage_summary.total_cost`는 `currency` 필드를 둔다. 본 계약도 `currency`를 유지했으나 **MVP에서 KRW 외 통화를 허용할지는 정하지 않았다.** 다중 통화를 허용하면 `case`의 예산 비교에 환율이 끼어든다 → **Consumer Review 항목**(유소연·김대원).~~ → **종결 (2026-09-09, [이슈 #19](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/19) common/runtime 답변 · `docs/modules/case/decisions/budget-krw-normalization.md`. 이 문서 표기 정합 2026-10-02, 버전 유지).** MVP에서 budget 대상 `UsageRecord.cost`는 저장 전에 KRW로 정규화해 `cost.currency="KRW"`로 기록한다. provider-native 통화와 환율/요율 provenance는 `pricing_id`가 가리키는 versioned pricing artifact가 보존한다. 남은 것은 그 artifact의 위치와 FX source다(다음 항목).
- **가격표·환율(`pricing_id` → 단가/FX) artifact의 위치·schema와 개정 절차** — ~~`common/runtime` config가 소유한다고만 정했다. 파일 형식·이력 보관은 구현 세부.~~ **(2026-10-02 · 표기 정합)** 위치를 정하지 않았다(§5 `pricing_context` 아래 문단). `pricing_id`가 가리킬 versioned pricing/FX artifact의 위치·schema, KRW 환산 FX source, 이력 보관은 미결이다. `budget-krw-normalization.md` 「남은 것」은 이를 common/runtime 구현 시점에 결정한다고 둔다.
- **보관 기간.** `recording`의 보관·일괄 삭제 정책(v4 §8-4)이 사용자 원본에 대한 것이고, 비용 원장은 개인정보가 아니므로 다른 주기가 맞을 수 있다. **`purge_case`가 UsageRecord를 지우는지 정하지 않았다** → 정철원(보관·삭제)과 확인 필요.
- **`operation` 전체 값 목록** — 닫지 않는다. 모듈 접두어 규칙만 고정한다.
