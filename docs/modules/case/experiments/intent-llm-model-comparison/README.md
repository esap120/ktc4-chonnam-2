# intent-llm-model-comparison

**목적:** `research/llm-model-comparison-hint-extraction.md`가 남긴 미결 항목(§7) — 자연어 단서 구조화 호출에 GPT-5 Nano / Gemini 3.1 Flash-Lite / Claude Haiku 4.5 중 무엇을 쓸지 실측으로 결정하기 — 을 실행하는 실험 하네스와 고정 데이터셋.

**상태(2026-09-19 실측 완료):** 3개 후보 + judge 모델(Claude Sonnet 5) 전부 Elice ML API 경유로 정상 호출됨 — candidate 21건 + judge 21건 전부 `error=None`/`schema_valid=True`. 최종 모델 선택은 `docs/modules/case/decisions/intent-llm-model-selection.md` 참고. 이 절 아래 내용은 실측 이전 준비 상태를 그대로 보존한다(하네스 자체 사용법은 여전히 유효).

## 비용 — 12만 크레딧 예산 대비

Elice 모델 카드에서 확인한 단가(KRW/1M 토큰, `scripts/pricing.py`):

| 모델 | 입력 | 출력 |
| --- | --- | --- |
| GPT-5 Nano | 76 | 609 |
| Gemini 3.1 Flash-Lite | 380 | 2,283 |
| Claude Haiku 4.5 | 1,522 | 7,612 |

시드 7건 × 후보 3개 + judge 21건 기준으로 계산하면 **총 실행 비용은 ₩50 미만**(1 크레딧=₩1 가정 시 12만 크레딧의 0.05% 미만) — `search`와 예산을 나눠 써도 문제없는 수준이다. 10배 여유를 둬도 ₩500 이내.

**실측 결과(2026-09-19):** 후보 3개 실제 비용 합계 44.93 KRW(claude-haiku-4-5 34.21 + gpt-5-nano 8.34 + gemini-3.1-flash-lite 2.38) — 위 어림값과 같은 자릿수. judge(claude-sonnet-5) 비용은 `pricing.py`의 `KRW_PER_1M_TOKENS`에 없는 모델이라 집계에서 `None`으로 빠졌다(조용히 0으로 세지 않는다는 정책대로). **2026-10-04: judge 단가(Sonnet 5 · Opus 5)를 `pricing.py`에 넣어 이후 judge run부터 비용이 기록된다** — 48케이스 1회 판정 실측 Sonnet 5 약 ₩3,400 · Opus 5 약 ₩8,200(`results/judge-validation-robustness-v2.md` §6).

## 채점 방식 — 1차 가설, 실측 전 잠정

**2026-09-19 갱신 — judge를 실제로 21건 돌렸다(전부 `error=None`).** 아래 설계 논리(왜 LLM-judge를 골랐는지)는 실측 전에 세운 그대로 유효해서 안 고쳤다.

**2026-09-20 갱신 — 사람 스팟체크 완료.** 126개 필드 판정 중 5개(4%)만 `correct`가 아니었고, 4개는 데이터셋(`expected_notes`) 공백, 1개는 judge rubric 문제(같은 값인데 모델별로 다르게 판정)로 확인됐다 — 후자는 `JUDGE_SYSTEM_PROMPT`에 규칙을 추가해 고쳤다(아래 「채점 방식」·`decisions/intent-llm-model-selection.md` §9). LLM-judge 신뢰도는 이걸로 이번 v1 비교 목적엔 충분하다고 판단했다 — 이 판단을 `decisions/`로 올리지 않고 `experiments/`에 계속 두는 이유(v1 한정 임시 방편이라는 것)는 그대로 유효하다.

**2026-09-18 방향 전환:** LLM-judge를 채점 방식의 최종 답으로 보지 않는다. `decisions/intent-llm-eval-target-thresholds.md`의 딥리서치가 권고하고 지금 보기에도 정확도·비용 면에서 더 나은 방법은 **CorrectionRecord 기반 Field-level F1**이지만, 런칭 전이라 CorrectionRecord 실데이터가 없어서 지금 당장은 못 쓴다. 그래서 LLM-judge는 **이번 v1 모델 비교 한 번에만 쓰는 임시 방편**이고, 런칭 후 CorrectionRecord가 쌓이면 F1 기반으로 전환한다(아래 「다음 단계」).

**스키마 준수율만으로는 부족하다.** 세 후보(GPT-5 Nano / Gemini 3.1 Flash-Lite / Claude Haiku 4.5) 모두 Structured Outputs(JSON Schema strict mode)를 지원한다(`research/llm-model-comparison-hint-extraction.md` §5) — API가 스키마 위반 자체를 강제로 막아준다. 그러면 "스키마를 지켰는가"만 재면 세 모델 다 100%에 가깝게 나와서 모델 간 차이가 안 보일 수 있다. 그래서 이 실험은 스키마 준수율과 별개로, **추출 내용의 정확도**(원문에 있는 내용을 실제로 옳게 뽑았는지, 없는 내용을 지어내지 않았는지)를 측정 대상에 포함한다 — 이게 이 실험 설계 전체의 출발점이다.

**내용 정확도 채점 방법으로 LLM-judge를 선택한 이유.** 검토한 대안:

- 필드별 규칙 기반 채점(정규식/키워드 매칭): 비용은 가장 낮지만, `time_hint`·`vehicle_hint`처럼 자유 텍스트 필드는 "정답 문자열"이 하나로 고정되지 않아(예: "어제 18시쯤"을 "18시쯤"이라고만 뽑아도 맞다고 봐야 하는지) 케이스마다 규칙을 정교하게 미리 써둬야 하는 부담이 큼.
- 사람이 직접 pass/fail 라벨링: 가장 정확하지만, 프롬프트나 모델을 바꿔 재실행할 때마다 3개 모델 × N개 케이스를 매번 다시 사람이 봐야 해서 반복 실험(재실행이 전제인 locked dataset 취지)에 안 맞음.
- **CorrectionRecord 기반 Field-level F1**: 정확도·비용 면에서 가장 이득이라고 판단한다(`decisions/intent-llm-eval-target-thresholds.md` §3.2·§5의 딥리서치 권고와 일치 — LLM-judge보다 결정론적이고 저렴함). **다만 지금은 못 쓴다** — case가 아직 런칭 전이라 실사용자가 고친 이력(`CorrectionRecord`)이 하나도 없다(같은 문서 §1 마지막 줄, UCR도 같은 이유로 production 이후로 미룸). 그래서 이번 v1 모델 비교에는 쓸 정답지가 없다.
- **LLM-judge(런칭 전 v1 비교용 임시 방편)**: 위 이유로 CorrectionRecord F1을 지금 못 쓰니, 이번 3개 모델 비교 한 번만 쓸 임시 채점 방식으로 LLM-judge를 둔다. 자유 텍스트의 의미적 동치를 판단할 수 있으면서 재실행 비용이 낮다는 게 근거다. 단점(judge 자체의 신뢰성)은 판정의 일부를 사람이 스팟체크하는 것으로 보완할 **계획**이지만, 그 스팟체크를 아직 안 해봤다. **런칭 후 CorrectionRecord가 쌓이면 LLM-judge는 걷어내고 Field-level F1로 전환한다** — 이번 하네스(`schema.py`/`judge.py`/`aggregate.py`)는 v1 모델 선정이 끝나면 그 역할을 다한 것으로 본다.

**"correct/partial/wrong" 하나로는 부족해서 hallucinated/missed로 더 쪼갰다.** 단순 정확도만 보면 "모델이 없는 내용을 지어냈다"와 "모델이 있는 내용을 놓쳤다"가 똑같이 "틀림"으로 뭉개진다. 이 둘은 원인도 다르고(전자는 과감함, 후자는 소극적 과묵) 신고 준비 맥락에서 위험도도 다르다(있지도 않은 차량 색상을 지어내는 쪽이 더 위험하다). 그래서 judge 판정을 `correct / partial / hallucinated / missed` 4종으로 나누고(`schema.py`), `aggregate.py`에서 다음을 모델별로 집계한다:

- `schema_compliance_rate` — 스키마 준수율
- `field_accuracy_rate` — 필드별 정확도(위 원래 채점 방식)
- `hallucination_rate` — 없는 정보를 지어낸 비율
- `missed_rate` — 있는 정보를 null로 놓친 비율(= null/UNKNOWN 처리가 안 된 비율)
- `per_scenario_accuracy` — 카테고리별 정확도. 데이터셋에 이미 있는 7개 태그를 그대로 써서 "애매한 표현 처리 정확도"(`전부_모호`·`차량_애매`·`위치_애매`)와 "correction 후 값 반영 정확도"(`잘못_입력_후_correction`)를 전체 평균에 묻히지 않고 따로 뽑는다.

## 이 데이터셋과 Mock Pack의 차이

`data/mock/case/scenario_happy_*.json`은 workflow/contract 검증용이고 `hints` 필드가 이미 구조화된 결과물이다(원문 문장이 없음). 이 폴더의 데이터셋은 **원문 문장 → LLM 추출 결과**를 실측하기 위한 것이라 목적이 다르다. `phase1-completion-checklist.md` 74번 항목이 명시한 "AI 실측은 1차 Mock 범위 밖"이 이 작업이다. 두 데이터는 서로 대체하지 않는다.

## Locked Dataset 정책

`datasets/intent-hint-eval-v1.jsonl`은 **고정(locked)** 세트다.

- 어떤 모델/프롬프트를 실측하든 이 파일을 그대로 재사용한다. 비교 대상이 바뀔 때마다 케이스를 새로 쓰면 이전 실측과 비교가 깨진다.
- 케이스를 추가/수정해야 하면 파일을 고치지 않고 `intent-hint-eval-v2.jsonl`을 새로 만든다. 이전 버전으로 만든 `predictions/`·`results/`는 그대로 보존한다.
- 버전 변경 사유는 이 README에 짧게 추가한다.
- **`intent-hint-robustness-v3.jsonl`(2026-10-05, 100케이스)** — 멘토 피드백 Q2(데이터 증강 · 지식 증류). 기존 55건을 seed로 Claude Opus 5.5(Claude Code)가 만들었다(지원금 소모 없음). robustness 10개 카테고리 × 8 + 정상 계열 20. 행마다 규칙 채점용 구조화 정답 `expected`(+ 여러 사건은 `events`)가 있다 — 형식 · 생성 규칙은 `datasets/intent-hint-robustness-v3.SPEC.md`, 검증 과정 · 한계는 `results/consistency-robustness-v3.md`. v1 · v2 파일은 그대로다.

### 카테고리 (최소 고정 — v1은 카테고리당 1케이스)

| 카테고리 | 왜 필요한가 |
| --- | --- |
| 정상 단서 | 모든 필드가 명확한 기준선 케이스 |
| 일부 누락 | 언급 안 된 필드를 null로 두는지, 지어내지 않는지 확인 |
| 전부 모호 | `confidence: low`를 실제로 붙이는지 확인 |
| 상대시간 표현 | "30분 전"처럼 상대 시간을 절대 시각으로 함부로 변환하지 않고 원문 그대로 보존하는지 확인(시각 해석은 case/evidence의 후속 책임) |
| 차량 애매 | 애매한 설명을 확정적인 값으로 지어내지 않는지 확인 |
| 위치 애매 | 위와 동일하되 위치 필드 |
| 잘못 입력 후 correction | 1회 호출 제한 하에서 `correction_target`을 올바르게 잡는지, 언급 안 된 다른 필드까지 덩달아 채우지 않는지 확인 — `prior_hints`로 이전 상태를 프롬프트에 준다 |

각 row의 `expected_notes`는 모델이 뱉어야 할 정확한 문자열이 아니라 judge가 채점할 때 참고하는 사람이 쓴 판정 기준이다(자유 텍스트 필드는 문자열 완전일치로 채점할 수 없음).

## 실험 원본 저장 (2026-10-05~)

모델 출력 · judge 판정 JSON은 레포에 두지 않는다(멘토 리뷰 #146 — 결과는 문서로, 큰 원본은 공용 저장소로). 실험마다 zip으로 묶어 [팀 공유 드라이브](https://drive.google.com/drive/folders/1Aeo_kkCzfJ9uhdMjb0GlLK2L3XqL80BR)에 두고, 결과 문서 첫머리 「원본」 줄에 파일 이름을 적는다. 폴더의 `.gitignore`가 원본이 다시 들어오는 것을 막는다. 이 정책 전에 커밋된 `predictions/` · `predictions-robustness/` · `predictions-robustness-v2/` 첫 실행분은 그대로 둔다.

## 하네스 구조

```
requirements.txt  # openai SDK (Elice가 OpenAI 호환 인터페이스로 중계 — 공유 pyproject.toml엔 안 넣음)
scripts/
  schema.py      # §3 추출 스키마(Pydantic) + 후보/judge 프롬프트 템플릿 (단일 정의 소스)
  pricing.py     # Elice 크레딧 단가(KRW/1M 토큰) → 호출당 비용 추정
  dataset.py     # datasets/*.jsonl 로더
  candidates.py  # CandidateAdapter/JudgeAdapter — Elice(OpenAI SDK 호환) 호출
  runner.py      # dataset × candidates → predictions/*.jsonl (불변 저장)
  judge.py       # predictions × judge 모델 → 필드별 {verdict, reason} 판정,
                 # predictions/<model>/<case_id>.judge.<run_id>.json로 run_id마다 분리 저장(덮어쓰지 않음)
  aggregate.py   # 스키마 준수율 · 필드 정확도율 · hallucination/missed rate · 카테고리별 정확도 ·
                 # 애매 3종 confidence:low 인정 비율 · 비용/latency 집계 → results/summary.md
                 # (--judge-run-id로 어느 채점 run을 집계할지 명시해야 함)
```

Prediction과 Judging을 분리해서, judge rubric이 바뀌어도 유료 API 호출(prediction)을 다시 하지 않아도 되게 한다.

**Judge 모델**: 비교 대상 3개 후보 중에서 고르지 않는다(자기 채점 편향 방지) — `judge.py`가 `JUDGE_MODEL`이 `MODEL_IDS` 안에 있으면 실행을 막는다. 실측(2026-09-19)에는 `anthropic/claude-sonnet-5`를 썼다(후보 중 최고가인 Claude Haiku 4.5보다 한 단계 위 티어).

**채점 결과는 run_id별로 분리 저장하고 덮어쓰지 않는다(2026-09-19, 멘토 피드백)** — "채점 프로세스도 바뀔 수 있으니까요"라는 이유로, `judge.py`를 다시 돌려도(rubric·judge 모델을 바꿔서 재채점해도) 이전 run의 파일이 그대로 남는다. `judge.py`가 끝나면서 찍는 `run_id`를 `aggregate.py --judge-run-id`에 그대로 넘겨야 한다.

**필드별 판정에 근거(`reason`)를 같이 저장한다(2026-09-19, 멘토 피드백)** — "결과만 있으면 틀린 케이스를 정성적으로 이해하기 어렵다"는 이유로, `JudgeVerdict`의 각 필드가 `{verdict, reason}` 쌍이 됐다(예전엔 6개 필드 판정 전체에 `notes` 하나만 공유). 후보 쪽 `IntentHintExtraction`에도 `reasoning` 필드를 추가해 같은 이유로 판단 근거를 남긴다.

**검증**: judge 판정 중 일부(20% 권장)를 사람이 직접 스팟체크한다. 사람과 다르게 판정한 케이스가 나오면 데이터셋이 아니라 `schema.py`의 judge 프롬프트(rubric)를 고친다.

**2026-09-20 스팟체크 결과**: 126개 필드 판정 중 5개(4%) 불일치 — 4개는 데이터셋 `expected_notes` 공백(v2에서 보완 예정), 1개는 rubric 문제(동일 값인데 모델별로 다르게 판정 — "같은 값이면 같은 verdict" 규칙을 `JUDGE_SYSTEM_PROMPT`에 추가해 고침). GPT-5 Nano는 5건과 무관. 상세는 `decisions/intent-llm-model-selection.md` §9.

## Elice 연동

세 모델 다 Elice가 **OpenAI SDK 호환 인터페이스**로 중계한다(`Authorization: Bearer <Serverless API Key>` + `client.chat.completions.parse(model=..., response_format=<PydanticModel>)`, 2026-09-19 실측으로 세 모델 다 구조화 출력까지 정상 확인됨). `candidates.py`는 벤더별 분기 없이 `model_name`만 다른 하나의 클래스로 세 모델을 다 처리한다.

**⚠️ base_url은 모델마다 다르다(2026-09-19 정정)** — 처음엔 세 모델이 base_url 하나를 공유한다고 가정했는데(Claude 카드 하나만 보고 세운 추측), 실제 모델 카드를 보니 `https://mlapi.run/<uuid>/v1`의 UUID 자체가 모델마다 다르다. API 키는 계정 공용으로 확인됨(모델별로 다르지 않음).

**실행 전 필요한 환경변수(`.env`, `candidates.py` 참고):**

| 변수 | 값 |
| --- | --- |
| `ELICE_API_KEY` | Elice ML API Serverless API 키 — 모델 공용 |
| `ELICE_URL_GPT_5_NANO` | GPT-5 Nano 모델 카드의 `https://<uuid>/v1` |
| `ELICE_URL_GEMINI_3_1_FLASH_LITE` | Gemini 3.1 Flash-Lite 모델 카드의 `https://<uuid>/v1` |
| `ELICE_URL_CLAUDE_HAIKU_4_5` | Claude Haiku 4.5 모델 카드의 `https://<uuid>/v1` |
| `JUDGE_MODEL` | 후보 3개 밖의 Elice 모델 ID — 이번 실측에 `anthropic/claude-sonnet-5` 사용 |
| `JUDGE_MODEL_URL` | 그 judge 모델의 `https://<uuid>/v1` |

키는 채팅에 붙여넣지 않고 `.env`나 셸 환경변수로 설정한다. `.env`는 `.gitignore`(`.env`/`.env.*` 패턴)에 걸려 커밋되지 않는다.

## 다음 단계

- [x] `ELICE_*_URL` 실제 값 확보 — 모델별로 다르다는 것까지 포함해 확인됨(위 「Elice 연동」)
- [x] `candidates.py`의 `MODEL_IDS` 문자열 확인 — `gemini-3.1-flash-lite`/`claude-haiku-4-5`는 모델 카드 예제로, `gpt-5-nano`는 실제 호출 성공(`schema_valid=True`)으로 확인됨
- [x] `response_format=<PydanticModel>` structured output이 Gemini/Claude 백엔드에도 강제되는지 확인 — **된다.** 21건 전부 `schema_valid=True`
- [x] `JUDGE_MODEL` 확정 — `anthropic/claude-sonnet-5`(후보 3개보다 위 티어, 자기 채점 편향 회피)
- [x] 실측 실행 → `results/summary.md`(2026-09-19, judge_run_id `20260919T170342Z`)
- [x] **채점 방식(LLM-judge) 자체를 재검토** — judge 판정 20% 스팟체크(2026-09-20 완료, 위 「검증」). 5/126(4%) 불일치, rubric 문제 1건은 고침.
- [x] 결과를 바탕으로 `docs/modules/case/decisions/`에 확정 문서 작성 → `intent-llm-model-selection.md`(모델 선택 + 이번 v1 한정으로 LLM-judge를 썼다는 것 둘 다 기록)
- [ ] **(런칭 후) LLM-judge를 CorrectionRecord 기반 Field-level F1으로 전환.** `CorrectionRecord` 실데이터가 쌓이기 시작하면 착수 — 그 전까지는 착수 조건 자체가 안 갖춰진 상태라 미룬다. 전환되면 이 폴더의 `schema.py`/`judge.py`(judge 프롬프트·판정 로직)는 더 이상 안 쓰이고, `aggregate.py`의 정확도 계산만 정답지 소스를 CorrectionRecord로 바꿔 재사용할 수 있는지 검토한다.
- [x] **PM 재검토(2026-09-22) — 강건성(도메인 밖 입력·일관성) 카테고리 추가 + 실측.** `datasets/intent-hint-eval-v1.jsonl`은 전부 "진짜 사고 설명"이라는 전제 위에 있어 그 전제가 깨지는 입력(무관한 질문·인젝션·모순 정보 등)을 하나도 안 다뤘다는 지적. `datasets/intent-hint-robustness-v1.jsonl`(9카테고리×3변형=27케이스)로 별도 파일에 두고 3개 모델 전체 실측 완료 — v1의 GPT-5 Nano 우위가 재현 안 됨. 상세: `research/intent-llm-robustness-test-design.md` §10.
- [x] **4번째 후보 추가 — Gemini 3.8 Flash(2026-09-22).** search 모듈이 이미 실사용 중인 모델(`src/daesingo/search/config.py`)을 재사용, `MODEL_IDS`/`.env`에 추가하고 v1+robustness-v1 34케이스 전체 실측 — 4개 모델 중 가장 균형 잡힌 결과. `pricing.py`에 KRW 단가 아직 없음(Elice 모델 카드 직접 확인 필요). 상세: `research/intent-llm-robustness-test-design.md` §11.
- [ ] **50케이스 이상으로 확장 진행 중(2026-09-22).** `intent-hint-robustness-v2.jsonl`(30케이스, `정보_위치순서_편향` 카테고리 신설) 작성, 기존 9개 카테고리 변형 2개씩(18개) 추가 요청 진행 중 — 완료되면 v1(7)+robustness-v2(48)=55케이스로 4개 모델 재실측 예정. 실사용자급 문장 수집(설문) 계획은 `research/intent-hint-real-text-collection-plan.md`에 준비만 해둠(미실행). 상세: `research/intent-llm-robustness-test-design.md` §12.
