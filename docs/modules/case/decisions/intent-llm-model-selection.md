# 자연어 단서 구조화 LLM — Gemini 3.8 Flash 채택 (2026-09-22 재검토로 변경)

> **2026-10-05 확정 — 「미결 유지」 해제.** 멘토 피드백(Q1 judge 검증 · Q2 데이터 증강 · 반복 일관성 · Q3 confidence, #213 단일 점수) 후속 측정으로 Gemini 3.8 Flash를 확정했다. §13.

> **2026-09-22 갱신 — 최종 결정이 바뀌었다.** §1~§9는 2026-09-19 첫 결정(GPT-5 Nano)의 원문 그대로 보존한다(불변 저장 원칙) — 왜 그때 그렇게 판단했는지는 여전히 유효한 기록이다. **현재 채택은 §10~§11을 본다.**

> 결정일 2026-09-19(실측) · 담당 유소연(`case`) · Consulted 없음
> 근거: `experiments/intent-llm-model-comparison/results/summary.md`(judge_run_id `20260919T170342Z`) · `research/llm-model-comparison-hint-extraction.md` §5·§6·§9 · `decisions/intent-llm-eval-target-thresholds.md` §1

## 1. 결정된 것 (2026-09-19 — §10에서 철회됨)

**자연어 단서 구조화("사용자 자연어 단서를 구조화한다", `tech-spec.md` §1) 호출에 GPT-5 Nano를 쓴다.** Gemini 3.1 Flash-Lite / Claude Haiku 4.5는 채택하지 않는다.

## 2. 실측 결과 요약

`datasets/intent-hint-eval-v1.jsonl`(카테고리당 1케이스, 총 7케이스) 기준, Elice ML API 경유 실측(2026-09-19):

| model | schema 준수율 | field 정확도 | hallucination | missed | 평균 latency | 총 비용(KRW) |
| --- | --- | --- | --- | --- | --- | --- |
| **gpt-5-nano** | 100% | **100%** | **0%** | **0%** | 12,745ms | 8.34 |
| gemini-3.1-flash-lite | 100% | 93% | 2% | 0% | 2,676ms | 2.38 |
| claude-haiku-4-5 | 100% | 95% | 0% | 2% | 3,417ms | 34.21 |

필드별·카테고리별 전체 분해와 judge의 필드별 판정 근거(`reason`)는 `results/summary.md`와 그 안에 적힌 `predictions/<model>/<case_id>.judge.20260919T170342Z.json`에 있다 — 이 문서에 옮겨 적지 않는다.

## 3. 목표치 대조

`decisions/intent-llm-eval-target-thresholds.md` §1 목표치 대비, **3개 후보 전부 통과**했다(schema ≥99%/field ≥70~75%/hallucination ≤5%/missed ≤10%). 즉 이 목표치만으로는 세 후보를 가르지 못한다 — §1.1이 이미 경고한 대로 n=7(필드 단위 n=42)이 작아 퍼센트 차이(93%~100%)를 소수점 단위로 믿지 않는다. 그래서 최종 선택은 §4/§5의 정성적 근거로 갈랐다.

## 4. 왜 GPT-5 Nano인가 — 다른 두 후보를 제외한 이유

- **Gemini 3.1 Flash-Lite 제외 이유**: (1) `research/...` §5가 이미 지적한 **Preview 상태** — GA 전환 전까지 프로덕션에 커밋하기엔 이르다는 우려가 실측과 무관하게 그대로 남아있다. (2) 실측에서도 `vehicle_hint`(86%)·`confidence`(71%) 필드가 셋 중 가장 약했고, 애매 3종 `confidence:low` 인정률도 2/3로 유일하게 100% 미만이었다 — "애매하면 확정하지 않는다"는 이 기능의 핵심 안전장치를 가장 못 지켰다.
- **Claude Haiku 4.5 제외 이유**: (1) 셋 중 최고가(₩34.21, GPT-5 Nano의 약 4.1배) — 이 볼륨에서 절대액은 작지만 세 후보 품질이 비슷한 이상 비용 차이가 그대로 감점 요인이다. (2) "상대시간_표현" 카테고리에서 67%로 셋 중 가장 낮았다 — 이 카테고리는 스키마 설계 자체가 "상대 시간을 절대 시각으로 임의 변환하지 않고 원문 그대로 보존"을 목표로 두는 지점이라(README "카테고리" 표) 가벼운 실패가 아니다.
- **GPT-5 Nano를 고른 이유**: 필드 정확도 100%(측정된 모든 필드·모든 카테고리에서 만점), hallucination/missed 둘 다 0%, 애매 3종 `confidence:low` 인정률 3/3. `research/...` §6의 "실측 우선순위 1순위"(최저가권 + 종료 공지 없음) 추천과도 일치한다 — 추천이 실측으로 확인된 사례다.

## 5. Latency 트레이드오프 — 이 결정에서 가장 중요한 단서

GPT-5 Nano는 평균 12,745ms로 나머지 둘(2,676ms/3,417ms)보다 **3.7~4.8배 느리다.** `research/...` §5의 후보 비교표엔 애초에 latency 축이 없었다 — 이번 실측이 드러낸 조사 공백이다.

그럼에도 채택하는 이유: `module-architecture.md` §1-5 원칙("긴 작업은 HTTP 요청 안에서 끝내지 않는다. API는 작업을 발주하고 `202 Accepted`를 반환하며 Worker가 처리한다")과 `architecture-input-memo.md` §2("intent LLM 호출은 1회로 제한")를 같이 보면, 이 호출은 **한 요청 안에서 동기로 끝내야 하는 게 아니라 1회짜리 비동기 Job으로 발주될 대상**이다. 12초 남짓의 단일 호출은 이 아키텍처 전제 위에서는 병목이 아니다 — 사용자가 붙잡혀 기다리는 게 아니라 `CaseView`의 진행 상태(`progress[]`)로 표시되는 백그라운드 작업의 하나가 된다.

**단, 이 판단이 깨지는 조건은 §7 재검토 트리거에 명시한다.**

## 6. 이미 다른 문서가 정한 것 (여기서 다시 정하지 않는다)

- 추출 스키마(`time_hint`/`vehicle_hint`/.../`reasoning`) — `research/llm-model-comparison-hint-extraction.md` §3.
- 이번 v1 비교에 LLM-judge를 쓴 이유와 그 한계(런칭 후 CorrectionRecord 기반 F1로 전환 예정) — `experiments/intent-llm-model-comparison/README.md` "채점 방식" 절.
- 평가 목표치 자체와 그 신뢰도 한계 — `decisions/intent-llm-eval-target-thresholds.md`.
- intent LLM 호출 1회 제한, case가 다른 모듈의 프롬프트/정책을 알면 안 된다는 경계 — `architecture-input-memo.md` §2 · `tech-spec.md` §1.

## 7. 재검토 트리거

아래 중 하나라도 실제로 생기면 다시 조사한다.

- [ ] intent 구조화 호출이 실제 구현에서 동기(사용자가 화면에서 기다리는 경로)로 붙게 된다 — §5의 latency 정당화가 성립하지 않게 되는 경우.
- [ ] Gemini 3.1 Flash-Lite가 GA로 전환된다 — §4의 제외 이유 중 하나(Preview 리스크)가 사라진다.
- [x] ~~v2 이상의 더 큰 locked dataset으로 재측정했을 때 이번 v1(n=7) 결과와 다른 순위가 나온다.~~ — **2026-09-22 충족.** 실사용자 로그 기반 v2는 아직이지만, `research/intent-llm-robustness-test-design.md`(9카테고리×3변형=27케이스, 강건성 관점)로 3개 모델을 재측정한 결과 v1의 100%/0% 우위가 재현되지 않았다(3개 모델 82~85%로 사실상 동률, hallucination 9~11%로 동반 상승, latency 격차는 오히려 확대). 스팟체크로 GPT-5 Nano의 실제 약점(새사고를 정정으로 오인, 3/3 hallucinated)도 확인됨(같은 문서 §10). 모델 재선정 여부는 별도 논의로 진행 — 이 트리거 충족 자체가 재선정 결론은 아니다.
- [x] ~~judge 판정 20% 스팟체크에서 LLM-judge가 사람과 크게 갈려, 이번 실측 자체의 신뢰도가 흔들린다~~ — 2026-09-20 완료, 안 흔들림(§9). 트리거 조건 미충족.
- [ ] `CorrectionRecord` 실데이터가 쌓여 Field-level F1로 채점 방식이 바뀐 뒤, 그 정답지로 다시 봤을 때 순위가 바뀐다.

## 8. 남은 것 — 이 결정이 안 끝낸 일

- **실제 프로덕션 배선은 이 결정의 범위 밖이다.** `CaseAggregate.intake()`가 아직 구조화된 `hints`만 받고, 원문 자연어를 GPT-5 Nano로 실제 호출하는 코드는 `domain.py`/`scope.py` 어디에도 없다 — 이건 별도 구현 작업(설계 고도화 우선순위 목록 3순위)이다.
- `research/...` §4 테스트 문장을 실사용자 로그로 교체(v2 dataset) — 미결. §9가 찾은 case-04류 위치 단서 판정 기준 공백도 v2에서 같이 메운다.
- Elice 쪽 `ELICE_API_KEY`/`ELICE_URL_*`/`JUDGE_MODEL_URL` 실제 값은 `.env`(gitignore 대상)에만 있고 이 문서·리포 어디에도 값 자체를 남기지 않는다.

## 9. judge 판정 스팟체크 결과 (2026-09-20)

126개 필드 판정(3모델 × 7케이스 × 6필드) 중 **5개(4%)만 `correct`가 아니었다** — 전부 `case-04-relative-time`/`case-05-vehicle-ambiguous` 두 케이스, claude-haiku-4-5/gemini-3.1-flash-lite 두 모델에만 있었다. **GPT-5 Nano는 5건과 전부 무관(126개 다 correct)** — 이 결정(§1)에 영향 없음.

5건을 사람이 직접 읽고 원인을 둘로 나눴다:

- **4건(case-04, location_hint/confidence)** — judge 판정 자체보다 **데이터셋 결함**이었다. `expected_notes`가 이 케이스의 `time_hint` 기준만 적어두고 원문의 "여기서"를 `location_hint`로 어떻게 다뤄야 하는지는 아예 안 정해뒀다 — judge가 그 자리에서 즉석 기준을 만들어 판정한 것. v2 데이터셋에서 이 공백을 메운다(§8).
- **1건(case-05, `vehicle_hint`)** — **진짜 judge 리스크**였다. claude·gemini 둘 다 `vehicle_hint="SUV"`로 완전히 같은 값을 냈는데 judge가 다르게 판정했다(claude: correct, gemini: partial) — gemini가 `confidence`를 잘못(`high`로) 매긴 여파가 무관한 `vehicle_hint` 판정에도 전이된 것으로 보인다. **조치:** `schema.py`의 `JUDGE_SYSTEM_PROMPT`에 "같은 필드가 같은 값이면 모델이 달라도 같은 verdict를 매긴다"는 규칙을 명시적으로 추가했다(이 커밋). 기존 `judge_run_id=20260919T170342Z` 결과는 그대로 두고(불변 저장 원칙, `judge.py` 참고) 덮어쓰지 않았다 — 이 rubric 수정은 다음 채점 run부터 적용된다.

**결론: 5/126(4%)이라는 이견율은 낮고, 유일한 진짜 judge 문제(case-05)도 이번 결정을 뒤집지 않는다 — §1의 GPT-5 Nano 채택은 이 스팟체크로 재확인됐다.**

> **2026-10-04 정정 — 이 스팟체크가 실제로 한 일.** judge가 `correct`가 아니라고 한 5개만 읽었고, `correct` 판정 121개의 표본 기록은 없으며 사람과 judge의 일치도는 재지 않았다. 「20% 스팟체크」라는 표현과 다르다. 48케이스에서의 judge 검증은 §12.

---

## 10. 재검토 결과 — 최종 결정 변경 (2026-09-22)

**§7 재검토 트리거("더 큰 dataset으로 재측정했을 때 다른 순위가 나온다")가 실제로 발동됐다** — PM이 §1의 표본 크기(n=7)를 지적한 뒤 강건성 데이터셋을 3차례에 걸쳐 실측했다(`research/intent-llm-robustness-test-design.md` §10~§13). 세 번 다 GPT-5 Nano의 §1 우위가 재현되지 않았고, 순위는 일관되게 같은 방향을 가리켰다.

| 실측(케이스 수) | GPT-5 Nano | Gemini 3.1 Flash-Lite | Claude Haiku 4.5 | Gemini 3.8 Flash |
| --- | --- | --- | --- | --- |
| robustness v1(27) | 85% / halluc 10% / 17.5s | 85% / 9% / 1.9s | 82% / 11% / 3.0s | **91% / 6% / 4.4s** |
| robustness v2(48) | 85% / 9% / 16.9s | 87% / 8% / 1.7s | 89% / 8% / 2.7s | **93% / 4% / 3.9s** |
| `새사고_정정오인_방지`(v1→v2) | 61%→70% (최저) | 78%→70% | 94%→93% (최고) | **100%→97%** |

(field 정확도 / hallucination rate / 평균 latency 순. 원본: `results/summary-robustness-v1.md`·`summary-robustness-v2.md`·`summary-gemini-3.8-flash-v1.md`·`summary-gemini-3.8-flash-robustness.md`.)

### 결정: GPT-5 Nano 채택을 철회하고 Gemini 3.8 Flash로 교체한다

**이유:**

1. **§1의 근거 자체가 착시였다.** "field 정확도 100%, hallucination 0%"는 n=7 표본에서 나온 숫자였고(§9의 스팟체크는 judge 신뢰도만 확인했을 뿐 표본 크기 문제는 다루지 않았다), 27~48케이스로 늘리자 GPT-5 Nano는 다른 후보와 사실상 동률(82~89% 사이)로 좁혀졌다.
2. **GPT-5 Nano가 오히려 correction 안전성에서 가장 약했다.** `새사고_정정오인_방지`(prior_hints가 있을 때 "이건 새 사고다"라는 신호를 정정으로 오인하지 않는지)에서 4개 모델 중 최저(61%)를 기록했다 — 스팟체크로 사람이 직접 원인 확인(judge rubric 문제 아니라 실제 모델 약점, `research/...` §10).
3. **§5의 latency 트레이드오프가 더 나빠졌다.** "12.7초는 비동기 job이라 괜찮다"는 논리는 그대로지만, 실제 latency가 처음 추정보다 더 벌어졌다(16.9~17.5초, Gemini 3.8 Flash 대비 4~9배). 품질 우위가 사라진 상태에서 이 격차만 남았다 — PM이 "latency가 마냥 긍정적으로 안 보인다"고 지적한 지점이 맞았다.
4. **Gemini 3.8 Flash는 3차례 실측 전부에서 최고 또는 최상위권**이었다(field 정확도·hallucination 둘 다) — 특히 GPT-5 Nano가 가장 약했던 correction 안전성 카테고리를 가장 잘 처리했다(97~100%).
5. **§4가 Gemini 3.1 Flash-Lite를 배제한 이유(Preview 상태)가 3.8 Flash에는 없다.** 2026-09-02 GA 전환 확인(Google 공식 발표, WebSearch로 검증). search 모듈이 이미 Elice로 실사용 중인 모델이라 신규 벤더 온보딩 비용도 없다(`src/daesingo/search/config.py`).

**하지 않은 것 — 비용 단가.** *(2026-10-05 해소: 입력 ₩1,141 · 출력 ₩5,709 / 1M 토큰, Elice 모델 카드 확인 — `scripts/pricing.py`, §13.)* Elice가 이 모델에 매기는 정확한 KRW 단가를 아직 못 구했다(`pricing.py`에 없음, Elice 모델 카드 직접 확인 필요 — 소연님 확인 대기). Google 공식 요율($0.75/$3.75)은 참고치일 뿐 Elice 마크업이 반영된 값이 아니다. 다만 search 모듈이 이미 이 모델을 실사용 중이라는 사실 자체가 팀이 감당 가능한 비용 수준이라는 간접 근거로 본다 — 확정 단가가 나오면 이 문서를 갱신한다.

**하지 않은 것 — 실사용자 로그 기반 확인.** §1이 원래 갖고 있던 표본 문제(실사용자 로그로 재측정)는 아직 실행 전이다(`research/intent-hint-real-text-collection-plan.md`, 설문 계획만 준비됨). 다만 세 번의 독립적인 synthetic 실측(27/34/48케이스, 서로 다른 케이스 구성)에서 순위가 일관되게 나왔다는 것으로, 이 확인을 기다리지 않고 지금 결정을 내려도 된다고 판단했다 — 실사용자 로그 실측이 나중에 다른 결과를 보이면 §11 트리거로 다시 연다.

## 11. 재검토 트리거 (2026-09-22 갱신)

- [ ] 실사용자 로그 기반 실측(`research/intent-hint-real-text-collection-plan.md` 실행 후)에서 이번 순위와 다른 결과가 나온다.
- [x] ~~Elice 모델 카드에서 확인한 실제 KRW 단가가 예상보다 크게 벗어나(다른 후보 대비 비용 열위) 재검토가 필요해진다.~~ — **2026-10-05 확인, 재검토 불필요.** Flash-Lite 대비 호출당 약 6.8배(₩3.0 vs ₩0.45)지만 case당 1~3회라 차이가 몇 원이고, 판단 기준(단일 점수 차 0.02 이내일 때만 비용 비교)상 점수로 결정됐다. §13.
- [ ] Gemini 3.8 Flash가 sunset·요금 인상(2027-01-01부터 표준 요금 $1.5/$7.5로 2배 인상 예정 — Google 공식) 등으로 재검토가 필요해진다.
- [ ] `correction_target_오염_시도` 카테고리(4개 모델 다 47~53%로 낮음, Gemini 3.8 Flash도 예외 아님. **2026-10-04: 이 중 일부는 judge 오류였고 바로잡으면 57~67% — §12.** **2026-10-05 Q3 실험: 지금 프롬프트는 끼워 넣은 무관 사실로 필드를 덮어쓰고(Gemini 3.8 Flash 10/10) confidence도 low로 내지 않는다(0/10). 「무관 사실은 무시하고 low · 명시적 전환 신호는 새 사고」 두 규칙(v3)을 넣으면 덮어씀 0/10 · low 10/10이고 새 사고 · 정상 문장은 high 유지 — `experiments/intent-llm-model-comparison/results/q3-confidence-experiment.md`. 운영 프롬프트는 search 소유(#210)라 반영을 요청한다**)가 실사용에서 실제 문제로 드러난다 — 이건 특정 모델 약점이 아니라 이 실험 전체의 미해결 지점으로 남아있다.

---

## 12. judge 신뢰도 검증 (2026-10-04, 멘토 피드백 Q1)

48케이스 판정에서 표본 80개를 AI(Claude Opus 5.5)가 judge 판정을 보지 않고 다시 판정하고, 판정이 갈린 10개를 유소연이 판정했다. 상세 방법 · 수치 · 한계는 `experiments/intent-llm-model-comparison/results/judge-validation-robustness-v2.md`.

- AI 1차 판정과 judge의 일치율 77.5%(kappa 0.63). 갈린 10개에서 사람은 AI 쪽 6, judge 쪽 4를 골랐다.
- **확인된 judge 오류:** 정정 케이스에서 언급되지 않은 필드의 올바른 null을 「이전 값을 유지했어야 한다」며 틀렸다고 판정했다. 1,152개 중 11건, 모두 `correction_target_오염_시도`. 바로잡으면 이 카테고리가 47~53% → 57~67%, 채택 모델 Gemini 3.8 Flash 전체 정확도 92.7% → 93.4%.
- **§10의 채택 결정은 바뀌지 않는다** — 모델 순위가 그대로다.
- **한계:** AI와 judge가 같게 본 판정은 사람이 확인하지 않아, AI 둘(같은 Claude 계열)이 함께 틀린 비율은 모른다.
- **후속(같은 날):** judge 판정 기준에 위 규칙을 예시와 함께 명시하자 **Sonnet 5가 11건을 모두 바로잡았고**, 원래 기준의 Opus 5(Elice에 Opus 5.5 없음)도 11건을 모두 맞혔다. 사람 판정 10개 일치는 원래 Sonnet 4 · 보강 Sonnet 6 · Opus 7이지만 표본이 Opus 계열에 유리하게 뽑혀 우열 근거로 쓰지 않는다. Opus는 형식 실패 14/192, 비용 약 2.4배.
- **judge 운영:** 반복 실험은 보강 기준 Sonnet 5, 최종 확인만 Opus 5. 세 judge 모두 모델 순위가 같아 §10 결정은 그대로다.

---

## 13. 확정 — 단일 점수 기준 (2026-10-05, 멘토 피드백 Q2 · #213)

**결정: Gemini 3.8 Flash로 확정한다.** 「모델 선정 · 평가 체계 — 멘토 피드백 후 확정(`미결 유지`)」을 해제한다.

판단 기준은 측정 전에 등재했다(`intent-llm-eval-target-thresholds.md` §1.0 — 단일 점수 = 평균 필드 정확도 × 필드 일관성, 통과 조건 hallucination ≤5%). 측정은 robustness-v3(100케이스, 지식 증류로 생성) × 5회 × v3 프롬프트, 상세 `experiments/intent-llm-model-comparison/results/consistency-robustness-v3.md`.

| | Gemini 3.8 Flash | Gemini 3.1 Flash-Lite |
| --- | --- | --- |
| 단일 점수 | **0.941** | 0.884 |
| 평균 정확도 / 필드 일관성 | 97.1% / 96.9% | 93.3% / 94.7% |
| hallucination(통과 조건) | 0.5% 통과 | 2.4% 통과 |
| latency 평균 | 3.7초 | 1.8초 |
| 호출당 비용 | 약 ₩3.0 | 약 ₩0.45 |

**근거**
- 단일 점수 차 0.057 — 기준상 latency · 비용을 비교하는 범위(0.02 이내) 밖이라 점수로 결정된다.
- 비용 차이는 비율로 6.8배지만 금액이 작다. 단서 구조화는 case당 분석 시작 1회 + 조건 수정마다 1회(보통 1~3회)라 case당 차이가 몇 원이다. 같은 모델로 영상을 보는 search 비용에 비하면 작은 비중이다(search 쪽은 실측이 아니라 토큰 환산 추정).
- 틀렸을 때의 비용이 더 크다. 단서 구조화 결과는 AnalysisScope의 탐색 범위 · 대상이 된다 — 시각 · 장소를 잘못 뽑으면 영상 탐색을 엉뚱한 범위로 돌리고 사용자가 다시 탐색해야 한다. Flash-Lite가 처진 곳이 바로 모호 · 모순 · 인젝션이다(위치 애매 82% · 인젝션 85% · 모순 70%, 3.8 Flash는 100% · 98% · 83%).
- latency 차이(약 2초)는 비동기 Job이고 뒤따르는 영상 탐색이 분 단위라 체감되지 않는다.
- search와 같은 모델이라 provider 설정 · 단가 관리 · 장애 대응이 하나로 묶인다(#210 — provider는 Search가 소유).
- 이전 측정(robustness-v1 · v2, judge 3종)과도 순위가 같다.

**대안:** Gemini 3.1 Flash-Lite는 v3 프롬프트에서 hallucination 2.4%로 통과선 안에 들어왔다. 비용 압박이 생기면 바로 꺼낼 수 있는 대안이다.

**운영에 넘길 것(#210, Search public 함수)**
- 프롬프트 v3 규칙 두 줄(무관 사실 무시 · low, 명시적 전환은 예외).
- 출력 한도 여유와 한도 초과 재시도 — 이번 500회 중 1회 내부 추론 토큰 1,917개로 한도 2,000에 걸렸다.

**한계(결과 문서 §5)**: teacher · 재라벨러 · judge가 모두 Claude 계열이고 사람 확인은 일괄 승인이었다. 합성 데이터라 실사용 문장 정확도는 여전히 미측정이다.

### 재검토 트리거 (§11에 더함)
- [ ] 실사용량이 커져 intent 호출 비용이 search 대비 의미 있는 비중이 된다 → Flash-Lite(같은 하네스 · 같은 기준)로 다시 비교.
- [ ] 실사용 문장 세트로 잰 단일 점수가 합성 세트(robustness-v3)와 크게 다르다.
- [ ] Search public 함수의 실제 운영 프롬프트가 v3와 달라진다 → 같은 하네스로 다시 잰다.

## 14. challenger 검증 — GPT-6 Luna · reasoning effort (2026-10-06, #281)

**결정: 지금 설정을 유지한다** — Gemini 3.8 Flash, `reasoning_effort`를 보내지 않는다(모델 기본값, §13 측정 조건 · #277 구현과 같다). **비용 대안은 Flash-Lite에서 GPT-6 Luna `none`으로 바꾼다.**

계기: Elice에 GPT-6 Luna(분류 · 추출용, 단가 3.8 Flash의 약 1/7)가 추가됐고, PM이 #278 리뷰에서 challenger 검증과 reasoning effort 비교를 제안했다. 같은 하네스 · 같은 기준(`intent-llm-eval-target-thresholds.md` §1.0)으로 쟀다. 상세 `experiments/intent-llm-model-comparison/results/luna-reasoning-effort-v3.md`.

| 설정 | 단일 점수 | 정확도 / 일관성 | hallucination | 지연 p50 / p95 | 호출당 비용 |
| --- | --- | --- | --- | --- | --- |
| **3.8 Flash 기본 (§13, 유지)** | **0.941** | 97.1% / 96.9% | 0.5% | 3.4 / 6.0초 | 약 ₩3.0 |
| 3.8 Flash `low` | 0.925 | 95.6% / 96.8% | 0.4% | 3.7 / 6.4초 | 약 ₩1.25 |
| 3.8 Flash `high` | smoke 탈락 — 10회 중 1회 출력 한도 초과 · 가장 느리고 비쌈 | | | | |
| **Luna `none` (새 비용 대안)** | 0.903 | 93.9% / 96.2% | 1.2% | 2.7 / 3.8초 | 약 ₩0.24 |
| Luna `low` · `high` | 0.890 · 0.889 | 94.7% / 94.0% · 93.9% | 1.1% · 1.2% | `high` 최대 66.2초 | 약 ₩0.29 · ₩0.34 |
| Flash-Lite (§13의 이전 대안) | 0.884 | 93.3% / 94.7% | 2.4% | 1.8 / 2.1초 | 약 ₩0.45 |

**근거**
- **Luna는 이기지 못한다.** 가장 좋은 `none`도 0.038 차이로 「0.02 이내」 밖이다.
- **3.8 Flash `low`는 점수 차 0.016으로 「0.02 이내」라, 규칙상 latency · 비용을 본다 — 비용은 약 59% 싸지만 바꾸지 않는다.** 「여러 사건 혼합」이 97% → 84%로 떨어졌다. 두 사건의 단서를 섞으면 영상 탐색을 엉뚱한 범위로 돌리는데, 이것이 §13에서 3.8 Flash를 고른 이유 자체다. 절감은 case당 약 ₩2~5로 작고, 지연도 줄지 않았다(p95 6.0 → 6.4초). 동점 규칙은 「전반 품질이 비슷할 때」를 위한 것이라 핵심 위험 카테고리에서 큰 하락이 있는 경우에는 적용하지 않았다. 두 측정의 날짜 · judge 실행이 달라 0.016에는 잡음도 섞여 있다.
- **Luna `none`을 비용 대안으로 둔다.** Flash-Lite보다 점수가 높고(0.903 vs 0.884) hallucination이 절반이며 비용도 절반이다. Luna는 추론을 늘릴수록 일관성이 떨어졌고(96.2% → 93.9%) `high`는 최대 지연이 search 실행 상한(60초, #277)을 넘어 쓰지 않는다.

**비용:** 약 ₩2,170(smoke ₩94 · 후보 ₩1,058 · judge Sonnet 5 ₩1,018). judge 몫을 ₩100~200으로 잘못 추정했다 — 판정 한 건 약 ₩17.5다.

### 재검토 트리거 (§13에 더함)
- [ ] 실사용 로그에서 「여러 사건을 한 설명에 적는」 입력이 드물다고 확인된다 → 3.8 Flash `low`(비용 약 59% 절감)를 같은 날 나란히 다시 잰다.
- [ ] intent 호출 비용이 의미 있는 비중이 된다 → 비용 대안은 Flash-Lite가 아니라 Luna `none`으로 비교한다(§13 첫 트리거 대체).
