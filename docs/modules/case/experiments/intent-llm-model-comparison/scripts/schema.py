"""단일 정의 소스: 추출 스키마 + 후보/judge 프롬프트.

스키마는 `research/llm-model-comparison-hint-extraction.md` §3과 동일해야 한다.
바꿀 일이 있으면 그 문서도 같이 갱신한다 (규칙 원문 중복 금지 — 여기 값이 실행에 쓰는 사본).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

FIELDS = (
    "time_hint",
    "vehicle_hint",
    "situation_hint",
    "location_hint",
    "correction_target",
    "confidence",
)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "time_hint": {"type": ["string", "null"]},
        "vehicle_hint": {"type": ["string", "null"]},
        "situation_hint": {"type": ["string", "null"]},
        "location_hint": {"type": ["string", "null"]},
        "correction_target": {
            "type": ["string", "null"],
            "description": "정정 대상 필드명. 새 정보면 null",
        },
        "confidence": {"type": "string", "enum": ["high", "low"]},
        "reasoning": {
            "type": "string",
            "description": "왜 이 값들을 뽑았는지 한두 문장 근거(멘토 피드백 2026-09-20 —"
            " 결과만 있으면 틀린 케이스를 정성적으로 이해하기 어려움)",
        },
    },
    "required": [*FIELDS, "reasoning"],
    "additionalProperties": False,
}


class IntentHintExtraction(BaseModel):
    """EXTRACTION_SCHEMA와 동일한 필드. Elice가 중계하는 OpenAI SDK의
    `response_format=<PydanticModel>` structured output에 이 클래스를 그대로 넘긴다.

    `reasoning`은 `FIELDS`(judge가 채점하는 6개 필드)에 안 들어간다 — 채점 대상이
    아니라 사람이 나중에 틀린 케이스를 정성적으로 읽어볼 때 참고하는 설명이다."""

    time_hint: Optional[str]
    vehicle_hint: Optional[str]
    situation_hint: Optional[str]
    location_hint: Optional[str]
    correction_target: Optional[str]
    confidence: Literal["high", "low"]
    reasoning: str


CANDIDATE_SYSTEM_PROMPT = """\
너는 교통위반 신고 준비를 돕는 시스템의 일부다. 사용자가 자연어로 말한 사고 상황 설명에서
아래 스키마의 필드만 추출한다.

규칙:
- 문장에 없는 내용을 지어내지 않는다. 언급 안 된 필드는 null로 둔다.
- 상대 시간 표현("30분 전" 등)은 절대 시각으로 임의 변환하지 말고 원문 표현을 그대로 담는다.
- 애매하거나 불확실한 진술은 confidence를 low로 표시한다. 되묻지 않는다(1회 호출).
- 이전 단서(prior_hints)가 주어지면, 이번 발화가 그중 하나를 정정하는지 판단해서
  correction_target에 정정 대상 필드명을 넣는다. 정정이 아니면 null.
- 이번 발화에서 언급되지 않은 필드는 prior_hints 값을 복사하지 말고 null로 둔다
  (병합은 이 호출의 책임이 아니다).
- reasoning에는 어떤 근거로 각 값을 그렇게 뽑았는지(특히 confidence를 low로 내린 이유,
  correction_target을 그 필드로 판단한 이유) 한두 문장으로 남긴다. 정답을 다시 나열하지
  않고 판단 과정을 설명한다.
"""

# Q3 실험용 후보 프롬프트 변형(멘토 피드백 2026-10-04 Q3 — 「정정에 무관한 정보를 끼워 넣으면 confidence가
# 낮게 나오는지 보고, 낮으면 서비스에서 재입력을 유도할 수 있다」). v1 규칙에 한 줄을 더한다. 기본 실험은 v1 그대로다.
CANDIDATE_SYSTEM_PROMPT_V2 = CANDIDATE_SYSTEM_PROMPT + """\
- prior_hints가 있을 때 정정 발화 안에 정정과 무관한 새 사실(다른 차량 · 다른 사건 등)이 섞여 있으면,
  그 새 사실로 필드를 채우거나 기존 값을 덮어쓰지 말고 무시한다. 이렇게 무관한 사실이 섞였거나
  정정 대상이 모호하면 confidence를 low로 표시한다.
"""

# v2는 Gemini 계열이 「명시적 새 사고」까지 무관 사실로 보고 무시 · low로 처리했다(Q3 실험 2026-10-05) — 예외를 더한다.
CANDIDATE_SYSTEM_PROMPT_V3 = CANDIDATE_SYSTEM_PROMPT_V2 + """\
- 단, "다른 건데요" · "그건 됐고" · "다 취소하고" · "또 다른 사고"처럼 명시적인 전환 신호가 있으면 정정이
  아니라 새 사고다. 이때는 위 규칙을 적용하지 않는다 — 새 발화 기준으로 필드를 채우고(correction_target은
  null), confidence는 진술이 분명한 정도대로 매긴다.
"""

CANDIDATE_USER_TEMPLATE = """\
prior_hints: {prior_hints_json}

사용자 발화: "{input_sentence}"
"""

VERDICTS = ("correct", "partial", "hallucinated", "missed")
"""필드별 judge 판정값. hallucinated/missed를 나누는 이유는
`README.md`의 "채점 방식 — 1차 가설, 실측 전 잠정" 참고 — hallucination rate와
null/UNKNOWN 처리 비율을 하나의 'wrong'에서 분리해서 보기 위함."""

Verdict = Literal["correct", "partial", "hallucinated", "missed"]


class FieldVerdict(BaseModel):
    """필드 하나에 대한 판정 + 근거. 예전엔 6개 필드 판정 전체에 `notes: str` 하나만
    공유했는데(2026-09-20 이전), 필드마다 왜 그렇게 판정했는지가 안 남아서 나중에
    틀린 케이스를 정성적으로 못 읽었다(멘토 피드백) — 그래서 필드마다 근거를 갖게 바꿨다."""

    verdict: Verdict
    reason: str


class JudgeVerdict(BaseModel):
    """judge 호출의 structured output 스키마. `IntentHintExtraction`과 마찬가지로
    `response_format=JudgeVerdict`로 그대로 넘긴다. 필드마다 `FieldVerdict`(판정+근거)를
    담는다 — `aggregate.py`는 `parsed[field]["verdict"]`로 판정값만, 근거는 사람이
    `predictions/`의 raw judge 파일을 직접 읽어서 참고한다."""

    time_hint: FieldVerdict
    vehicle_hint: FieldVerdict
    situation_hint: FieldVerdict
    location_hint: FieldVerdict
    correction_target: FieldVerdict
    confidence: FieldVerdict

JUDGE_SYSTEM_PROMPT = """\
너는 자연어 단서 추출 결과를 채점하는 평가자다. 비교 대상 모델 중 하나가 아니다.
아래 정보를 보고 필드마다 다음 네 가지 중 하나를 verdict로 매기고, 그 필드에 대한
reason(한두 문장 근거)을 같이 남긴다.

- correct: 원문 내용과 expected_notes 기준에 맞게 값을 뽑았거나, 없어야 할 값을 null로 뒀다.
- partial: 방향은 맞지만 일부만 맞다(예: 정정 필드는 맞았지만 confidence가 틀림).
- hallucinated: 원문에 없거나 애매하다고만 한 내용을 모델이 구체적인 값으로 지어냈다
  (값이 그럴듯해도 원문 근거가 없으면 hallucinated). correction 케이스에서 언급 안 된
  필드에 이전 값을 그대로 복사해 넣은 것도 hallucinated다(병합은 이 호출의 책임이 아님).
- missed: 원문에 명확히 있는 내용을 모델이 null로 빠뜨렸다.

채점 기준:
- expected_notes는 정답 문자열이 아니라 사람이 쓴 판정 기준이다. 문자열 완전일치를 요구하지 않는다.
- hallucinated와 missed는 방향이 반대다 — 헷갈리면 "모델이 원문보다 더 많이 말했는가(hallucinated)
  아니면 더 적게 말했는가(missed)"로 구분한다.
- **정정 케이스(prior_hints가 있음)에서 이번 발화가 언급하지 않은 필드는 null이 정답(correct)이다.**
  prior_hints에 값이 있어도 "이전 값을 유지했어야 한다"며 missed나 hallucinated로 판정하지 않는다 —
  이전 값과 합치는 것은 이 호출이 아니라 뒤의 병합 단계가 한다. 반대로 언급하지 않은 필드에 이전 값을
  채웠으면 hallucinated다. 예: prior_hints={"vehicle_hint": "흰색 SUV"}, 발화 "시간 그거 말고 19시였어요"
  → vehicle_hint=null은 correct, vehicle_hint="흰색 SUV"는 hallucinated(2026-10-04 judge 검증에서 이
  규칙을 어긴 판정 11건이 확인돼 명시했다 — `results/judge-validation-robustness-v2.md`).
- reason은 그 필드 하나에 대한 근거만 담는다(다른 필드 얘기를 섞지 않는다) — 나중에
  사람이 이 필드가 왜 이렇게 판정됐는지만 보고 이해할 수 있어야 한다.
- **같은 필드가 같은 값이면 모델이 달라도 같은 verdict를 매긴다.** 그 필드의 verdict는
  그 필드의 최종 값만 보고 정한다 — 모델이 남긴 reasoning(모델 출력에 같이 들어있을 수
  있음)에 불확실성을 인정했는지는 confidence 필드 자체를 판정할 때만 근거로 쓰고,
  다른 필드(예: vehicle_hint)의 verdict를 낮추는 데 전이시키지 않는다(2026-09-19 v1
  실측 스팟체크에서 발견 — 두 후보가 동일하게 `vehicle_hint="SUV"`를 냈는데 한쪽만
  `confidence`를 잘못 매긴 걸 근거로 `vehicle_hint`까지 다르게 판정한 사례가 있었다).

출력 형식 자체는 이 호출에 넘기는 response_format(JudgeVerdict) 스키마가 강제한다.
"""

JUDGE_USER_TEMPLATE = """\
[원문 발화]
{input_sentence}

[prior_hints]
{prior_hints_json}

[판정 기준 (expected_notes)]
{expected_notes}

[모델 출력]
{candidate_output_json}
"""


def validate_schema(obj: dict) -> tuple[bool, list[str]]:
    """EXTRACTION_SCHEMA에 대한 최소 수동 검증. 외부 jsonschema 의존성을 새로 추가하지 않기 위함
    (pyproject.toml에 pydantic만 있고, 이 실험은 case 공유 의존성에 손대지 않는다).

    `reasoning`은 `FIELDS`(judge 채점 대상 6개)에 없지만 `EXTRACTION_SCHEMA`엔
    필수 필드로 있다 — 여기서 따로 검증한다.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return False, ["출력이 JSON object가 아님"]

    allowed = set(FIELDS) | {"reasoning"}
    extra = set(obj.keys()) - allowed
    if extra:
        errors.append(f"스키마에 없는 필드: {sorted(extra)}")

    for field in FIELDS:
        if field not in obj:
            errors.append(f"필수 필드 누락: {field}")
            continue
        value = obj[field]
        if field == "confidence":
            if value not in ("high", "low"):
                errors.append(f"confidence 값이 enum 밖: {value!r}")
        else:
            if value is not None and not isinstance(value, str):
                errors.append(f"{field}는 string 또는 null이어야 함, 실제: {type(value).__name__}")

    if "reasoning" not in obj:
        errors.append("필수 필드 누락: reasoning")
    elif not isinstance(obj["reasoning"], str):
        errors.append(f"reasoning은 string이어야 함, 실제: {type(obj['reasoning']).__name__}")

    return (len(errors) == 0), errors
