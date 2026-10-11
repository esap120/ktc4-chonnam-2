# Timeout / Long-running Job Fallback — 담당과 결정 시점

> 결정일 2026-09-04 · 근거 `management/cross-cutting-decisions.md` A-1
> **담당:** 유소연(`case`) · **Consulted:** 신유민(`web`)
> **2026-09-28 잠정값 기재** — 이슈 #72, `search` 실측 `docs/modules/search/experiments/latency-baseline-2026-09-28.md`(#182, 서어진)
> **2026-09-29 클립 분할 범위 반영** — 이슈 #168 (c)
> **2026-10-03 표기 정합** — `core-user-flow.md` #168 결정 3 · #170 F에 맞춰 「이어서 찾기 = 남은 클립만 새 Job」 문구 폐기 · 현재 범위의 부분 후보 미보존 명시. 새 결정 아님(Runtime §5 검토 중 발견, case Owner 확인 요청 — #245)

## 결정된 것

- timeout 발생 여부와 작업 중단/계속 정책은 작업 lifecycle·orchestration 문제라 **`case`가 소유**한다.
- **timeout 수치는 baseline 실측 후에 정한다.** `search` Owner의 비용·지연 실측 결과가 나오면 이 문서에 값을 적는다. → 2026-09-28 현재 실행 경로(Elice 프록시) 실측으로 아래 **잠정값**을 적었다.

## 이미 다른 문서가 정한 것 (여기서 다시 정하지 않는다)

- **timeout·중단 시 무엇을 보여줄지**는 `product/core-user-flow.md` §7(분석 중단 — 현재까지 후보 유지 + `이어서 찾기` + `조건 수정`)과 §22(결과 없음 — 출구 4개)가 정했다. 「직접 타임라인」 화면은 두지 않는다(§22).
- runtime의 lease·heartbeat·retry timing은 `common/runtime`이 소유한다(`module-architecture.md` §2 원칙 6). `case`가 정하는 것은 「얼마나 기다린 뒤 부분 결과로 전환하는가」와 「그때 어떤 Job을 취소/유지하는가」다.
- search 실행 상한의 단일 권위는 `AnalysisScope.budget.max_latency_sec`다(#149 A안, #180). 아래 값은 case가 Job마다 이 필드로 넘기는 값이다. Fine은 후보를 만든 Coarse scope의 상한을 이어받아 호출마다 새로 센다(#180).
- **영상을 클립으로 나누는 범위와 나눈 뒤 후보 순서·경계 중복**은 #168이 정했다([Case 결정](https://github.com/kakaotechcampus-4/ktc4-chonnam-2/issues/168#issuecomment-5889291979)) — 인라인 상한 안의 영상은 클립 1개(Run 1개), 넘는 영상만 나눈다.

## 잠정값 (2026-09-28)

> **잠정.** 로컬 4코어 머신에서 잰 값이다. Coarse 시간의 절반 이상이 로컬 ffmpeg 전처리라 **runtime 머신에서 다시 재야** 확정할 수 있다(search Owner가 가장 중요한 미측정 항목으로 꼽음). 재측정 결과가 나오면 이 표를 갱신한다.

| 항목 | 잠정값 | 근거(#182 실측) |
| --- | --- | --- |
| Coarse 클립당 timeout (`COARSE_SEARCH` Job 하나의 `max_latency_sec`) | **150초** | 5분 클립 순차 wall p50 47.6초 · 최대 52.3초 · 재측정 62.0초 · 최악 68.5초(부하에 ±30%). 클립 상한 5.7~8.2분(인라인 12 MiB) → 8.2분 최악 추정 68.5 × 8.2/5 ≈ 112초 + provider 재시도 대기 최대 35초(429·5xx만, 5+10+20) ≈ 147초 |
| 클립 Job 동시성 (한 case 안) | **1** (순차 발주) | 같은 머신에서는 병목이 ffmpeg라 동시에 돌리면 클립당 시간이 늘어난다(동시성 1·4·8 → 클립당 59→203→341초, 전체는 1.3배 빨라질 뿐). 전처리가 다른 머신·코어로 나뉘면 다시 정한다 |
| Coarse 전체 timeout | **150초 × 클립 수** (나누지 않는 영상은 클립 1개라 150초) | 9/18 초안 공식 「클립당 × 클립 수 / 동시성」에서 동시성 이득이 없어 `/ 동시성`을 뺐다. 40분 영상(클립 8개) 최악 20분, p50 기준 약 8분(465초) |
| Fine 후보당 timeout (`VISUAL_VERIFY`) | **70초** | p50 8.5초 · p95 15.5초 · 최대 33.4초(길이 무관) + 재시도 대기 최대 35초 ≈ 68초. 9/18 초안(30~40초)은 재시도를 넣지 않은 값이라 올렸다 |

## timeout 시 유지/취소하는 Job 집합 (2026-09-28)

- **이미 끝난 탐색의 후보는 버리지 않는다.** core-user-flow §7 「현재까지 얻은 결과를 버리지 않는다」 그대로. 단 **현재 범위에서는 중단·timeout된 search run이 보존할 부분 Candidate를 남기지 않는다** — run 도중 timeout이면 그 run은 `FAILED`이고 후보가 없다(#72 search 답변). 구간 단위 부분 결과 보존은 그런 결과가 생긴 뒤의 동작이다(`core-user-flow.md` 「사용자가 분석을 중단한 경우」, #168 결정 3 · #170 F).
- **진행 중인 Job은 강제 취소하지 않고, case가 기다리는 것만 멈춘다.** UI는 부분 결과로 먼저 넘긴다. 이미 비용이 나간 호출을 버리지 않는다.
- **늦게 도착한 결과**는 결과물의 `candidate_id`가 현재 선택 후보와 맞을 때만 반영한다(#173 E-4 조건 2, `design-refinement-w7-baseline.md` 6.6순위).
- **timeout · 중단 뒤 `이어서 찾기`는 새 사용자 Intent다.** 새 `JobRecord` · 새 `job_id`로 발주하고([`job-resume-identity-policy.md`](./job-resume-identity-policy.md)), **영상 전체를 다시 보는 새 탐색**이다 — 안 본 구간만 이어 보는 동작이 아니다. 새 탐색의 후보는 이전 탐색의 후보와 섞지 않는다(`core-user-flow.md` 「사용자가 분석을 중단한 경우」 · §4-2, #168 결정 3 · #170 F). *(2026-10-03 표기 정합: 이전 문구 「남은 클립만 새 Job으로 발주 · 완료된 클립 Job은 다시 부르지 않는다」는 위 Product 결정과 맞지 않아 폐기.)*

## 남은 것

| 항목 | 상태 | 무엇으로 정하는가 |
| --- | --- | --- |
| 위 잠정값 확정 | 잠정 | runtime 머신 재측정(`common/runtime` 배치 후) |
| 클립 분할 발주 구현 | 미구현 | 지금 case는 영상을 클립으로 나누지 않고 Coarse를 한 번에 부른다(`real_e2e.py`, 상한 150초 — #200). 분할은 인라인 상한을 넘는 영상에만 필요하고(#168 (c)), 그 전에 #168에 남은 overlap 길이·중복 제거 호출 지점을 정한다 |
| 부분 재실행 정책 표와의 정합 | 미결 | `module-architecture.md` §7-4 |
