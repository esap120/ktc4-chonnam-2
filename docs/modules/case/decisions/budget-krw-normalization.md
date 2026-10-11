# 예산(KRW) vs 비용(USD) 통화 정규화 — 결정과 Mock 기본값

> 결정일 2026-09-09 · 근거 [이슈 #19](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/19) common/runtime 측 답변 · `docs/mock/05_mock_deep_review_report.md` P3-1
> **담당:** 유소연(`case`) · **Consulted:** 김준영(evidence/PM)

## 결정된 것 (이슈 #19, common/runtime 답변)

- 예산 판정의 authoritative source는 **`UsageRecord`**다. `AnalysisRun.usage_summary`는 파생 snapshot일 뿐 예산 비교에 쓰지 않는다(CALL-13 결정).
- MVP에서 budget 대상 `UsageRecord.cost`는 **저장 전에 KRW로 정규화**해 `cost.currency="KRW"`로 기록한다. provider-native 통화(예: gemini의 USD)와 환율/요율 provenance는 `pricing_id`가 가리키는 versioned pricing artifact가 보존한다.
- `AnalysisScope.budget.max_cost_krw`의 실제 숫자값은 계약이 아니라 benchmark/config 관리 대상이다(`contract-analysis-scope.md` §6).

## Mock에 적용한 값

**환율**: `1 USD = 1400 KRW`(2026-09 시점 근사치, 반올림). 이 값 자체는 실제 환율 API/계약이 아니라 **Mock Pack 한정 placeholder**이며, 실제 구현체는 `pricing_id`가 가리키는 실제 pricing/FX 소스를 따라야 한다. `pricing_context.pricing_id`에 `fx-krw-2026-09`를 추가해 이 환산이 어떤 환율 스냅샷을 썼는지 추적 가능하게 했다.

**변환 결과** (`SEARCH_COARSE` `UsageRecord.cost`, 소수점 반올림):

| 시나리오 | USD(기존) | KRW(정규화 후) |
| --- | --- | --- |
| `scenario_happy_001` | 0.42 | 588 |
| `scenario_unknown_abstain_partial_001` | 0.39 | 546 |
| `scenario_plate_reread_001` | 0.38 | 532 |
| `scenario_correction_rerun_001` | 0.33 | 462 |
| `scenario_empty_001` | 0.31 | 434 |

`READOUT_PLATE`/`READOUT_OVERLAY_TIME`(옛 `PLATE_OCR`/`OVERLAY_OCR`)의 `ocr-local` 비용은 이미 `{"amount":"0.00","currency":"KRW"}`라 변경 없음.

**추가 정규화(2026-09-10, 이슈 #23 B-1, 서어진 제안·본인 지지):** 위 표는 원장(`common/*.json`의 `UsageRecord.cost`)만 다뤘고, 같은 `AnalysisRun`을 search 쪽에서 내는 projected snapshot(`search/*.json`의 `AnalysisRunCandidateEvent.analysis_run.usage_summary.total_cost`)은 이 라운드 전까지 USD로 남아 있었다 — 값 자체(0.42×1400=588 등)는 원장과 정합했지만 `currency` 라벨만 달랐다. `AnalysisScope.budget.max_cost_krw`가 KRW 기준이고 eval이 efficiency 재계산에 `usage_summary`를 직접 쓰므로 라벨 불일치는 fx 없이는 예산 비교가 깨지는 실질적 gap이었다(계약 §3-4 "usage_summary는 run의 usage aggregate와 정합해야 한다"). 6개 시나리오(`happy`·`unknown_abstain_partial`·`plate_reread`·`correction_rerun`·`empty`·`relative_rebase`) 전체의 coarse/fine `usage_summary.total_cost.currency`를 `KRW`로, `amount`는 원장의 정수 KRW 값으로 맞췄다. `relative_rebase`(`0.06→84`)는 이 표에 없던 신규분이라 같이 반영.

## `budget.max_cost_krw` 기본값

기존 `300`은 위 실측 비용(최대 588 KRW)보다 낮아 **모든 시나리오가 예산을 초과**하는 상태였다(이슈 #15에서 서어진도 동일하게 지적). 기본값을 **`1000`**으로 올렸다 — 현재 최대 비용(588)에 여유를 두어, 다음 라운드에 추가될 `VISUAL_VERIFY`(Fine) run 비용이 더해져도 happy가 예산 내에 들어오도록 했다. 정확한 제품 기본값은 실제 벤치마크가 나오면 재조정한다(이 문서·계약 모두 "제품 기본 숫자는 benchmark/config 관리"라고 이미 명시).

## 남은 것

- **정규화 층과 `amount=null` (2026-10-05, [#244](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/244) U-2 결정).** KRW 정규화는 cost를 계산하는 층(Search)에서 한다 — Runtime은 `cost.currency == "KRW"`만 검증하고 환산하지 않는다. KRW 요율이 설정되지 않았으면 `amount=null`이고 **0이 아니다.** 그래서 case budget guard는 `amount=null`을 「계산 불가」로 다룬다 — 0으로 더하면 예산이 남은 것처럼 보인다. 「계산 불가」일 때 발주를 막을지 계속할지는 guard 구현 때 정한다(#244 U-2 「case 확인 범위」). FX 출처는 RD-08이 닫을 때까지 placeholder `pricing_id`다.
- 실제 환율/요율을 관리하는 versioned pricing artifact(현재는 `fx-krw-2026-09`라는 opaque id만 부여, 실제 조회 가능한 문서/서비스는 아직 없음) — common/runtime 구현 시점에 결정.
- ~~`VISUAL_VERIFY`(Fine) run이 추가되면(P0-3) 그 `UsageRecord.cost`도 이 규칙(KRW 정규화)을 그대로 따라야 한다.~~ → **완료**: Fine run 추가 시점에 원장은 처음부터 KRW로 냈고(위 표), 2026-09-10에 search의 `usage_summary` snapshot도 맞췄다.
- 이 문서는 fixture 정규화 기록이다 — `contract-analysis-run-candidate-event.md`의 `usage_summary.total_cost` 필드 정의 자체(허용 통화)는 아직 "정규화된 통화를 써야 한다"고 명문화하지 않았다. 계약 문서 정식 등재는 search 소유(서어진) 잔여 작업.
