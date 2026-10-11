"""Elice ML API 호출 어댑터.

Elice가 세 후보 모두 **OpenAI SDK 호환 인터페이스**로 중계한다는 걸 확인했다(사용자가
모델 카드에서 직접 확인):

- 인증: `Authorization: Bearer <Serverless API Key>` — OpenAI SDK가 `api_key=`로 자동 처리,
  계정 공용(모델마다 다르지 않음, 카드 표기로 확인)
- 호출: `client.chat.completions.create(model=..., messages=[...])` (Gemini 3.1 Flash-Lite
  스트리밍 예제로 확인) — payload가 OpenAI Chat Completions 형식인 건 맞다.
- **base_url은 모델마다 통째로 다르다(2026-09-20 정정)** — 처음엔 "세 모델이 base_url
  하나를 공유한다"고 가정했지만(Claude 카드 하나만 보고 세운 추측), 실제로는 모델 카드마다
  `client = OpenAI(base_url="https://<그 모델의 mlapi.run UUID>/v1", ...)`처럼 UUID
  자체가 다르다. 그래서 `_client()`는 이제 `model_name`을 받아 그 모델 전용 환경변수에서
  `base_url`을 찾는다 — 후보 3개는 `_MODEL_BASE_URL_ENV`, judge 모델은 `JUDGE_MODEL_URL`
  (`.env` 참고).

세 모델 다 같은 클래스(model_name만 다름)로 처리한다 — 벤더별 서브클래스가 필요 없어졌다.

**아직 확인 안 된 것:**
- `MODEL_IDS`의 `gemini-3.1-flash-lite`는 실제 카드 예제로 확인됐다. `gpt-5-nano`는
  아직 그 카드의 호출 예제로 직접 확인한 적이 없다(같은 명명 규칙일 거라는 추정만 있음).
- `response_format=<PydanticModel>` structured output(`.parse()`)이 Claude/Gemini
  백엔드에도 동일하게 강제되는지는 실제로 호출해봐야 안다 — 지금까지 본 모델 카드 예제는
  전부 `.create()` + `stream=True` 일반 채팅뿐이고 `.parse()` 예제는 못 봤다.
  `schema_valid`가 계속 False로 나오면 이 가정이 깨진 것이니 `runner.py` 출력을 먼저 본다.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from openai import OpenAI

from pricing import estimate_cost_krw
from schema import (
    CANDIDATE_SYSTEM_PROMPT,
    CANDIDATE_USER_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_USER_TEMPLATE,
    IntentHintExtraction,
    JudgeVerdict,
)

MODEL_IDS = {
    "gpt-5-nano": "gpt-5-nano",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",  # 스트리밍 예제로 확인됨
    "claude-haiku-4-5": "claude-haiku-4-5",  # 사용자가 모델 카드에서 직접 확인한 값
    "gemini-3.8-flash": "gemini-3.8-flash",  # search 모듈이 이미 실사용 중(config.py) — Preview 아님
    "gpt-6-luna": "openai/gpt-6-luna",  # #281 challenger(2026-10-06 Elice 추가, 유소연이 모델 카드에서 확인)
}

# 후보 4개의 model_name -> base_url을 담은 환경변수 이름. judge 모델(MODEL_IDS 밖)은
# 여기 없고 JUDGE_MODEL_URL 하나로 따로 처리한다(.env 참고).
_MODEL_BASE_URL_ENV = {
    "gpt-5-nano": "ELICE_URL_GPT_5_NANO",
    "gemini-3.1-flash-lite": "ELICE_URL_GEMINI_3_1_FLASH_LITE",
    "claude-haiku-4-5": "ELICE_URL_CLAUDE_HAIKU_4_5",
    "gemini-3.8-flash": "ELICE_URL_GEMINI_3_8_FLASH",
    "gpt-6-luna": "ELICE_URL_GPT_6_LUNA",
}


def _client(model_name: str) -> OpenAI:
    """base_url이 모델마다 다르므로(모듈 docstring 참고) `model_name`으로 골라야 한다.
    `model_name`이 후보 3개 중 하나면 그 전용 URL을, 아니면(judge 모델) `JUDGE_MODEL_URL`을
    쓴다 — judge 모델은 정의상 `MODEL_IDS` 밖의 모델 하나뿐이라 이름별 매핑이 필요 없다."""
    env_name = _MODEL_BASE_URL_ENV.get(model_name, "JUDGE_MODEL_URL")
    return OpenAI(
        api_key=os.environ["ELICE_API_KEY"],
        base_url=os.environ[env_name],
    )


@dataclass
class CandidateResult:
    model_name: str
    raw_text: str | None
    parsed: dict | None
    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_krw: float | None
    error: str | None
    # #281 smoke 확인용 — 추론 토큰(백엔드가 주지 않으면 None)과 종료 사유(`length`면 출력 한도에 걸림).
    reasoning_tokens: int | None = None
    finish_reason: str | None = None


class CandidateAdapter:
    """세 후보 모두 이 클래스 하나로 처리한다 — `model_name`만 다르게 인스턴스화."""

    def __init__(
        self, model_name: str, system_prompt: str = CANDIDATE_SYSTEM_PROMPT, reasoning_effort: str | None = None
    ):
        self.model_name = model_name
        # 프롬프트 변형 실험(Q3)용. 기본값은 v1 — 기존 runner 동작은 그대로다.
        self.system_prompt = system_prompt
        # #281 — `None`이면 인자를 보내지 않는다(모델 기본값). 기존 실험은 모두 None이었다.
        self.reasoning_effort = reasoning_effort

    def extract(self, input_sentence: str, prior_hints: dict | None) -> CandidateResult:
        user_prompt = CANDIDATE_USER_TEMPLATE.format(
            prior_hints_json=json.dumps(prior_hints, ensure_ascii=False),
            input_sentence=input_sentence,
        )
        start = time.monotonic()
        try:
            response = _client(self.model_name).chat.completions.parse(
                # 결과 폴더 · 단가표는 짧은 이름을 쓰고, 호출 ID가 다른 모델(`openai/…`)만 `MODEL_IDS`로 바꾼다.
                model=MODEL_IDS.get(self.model_name, self.model_name),
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=IntentHintExtraction,
                **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
            )
        except Exception as exc:  # noqa: BLE001 — 호출 실패도 결과로 기록해야 함
            return CandidateResult(
                model_name=self.model_name,
                raw_text=None,
                parsed=None,
                latency_ms=(time.monotonic() - start) * 1000,
                prompt_tokens=None,
                completion_tokens=None,
                cost_krw=None,
                error=str(exc),
            )
        latency_ms = (time.monotonic() - start) * 1000

        message = response.choices[0].message
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        parsed_model = getattr(message, "parsed", None)

        return CandidateResult(
            model_name=self.model_name,
            raw_text=message.content,
            parsed=parsed_model.model_dump() if parsed_model is not None else None,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_krw=estimate_cost_krw(self.model_name, prompt_tokens, completion_tokens),
            error=(
                None
                if parsed_model is not None
                else (getattr(message, "refusal", None) or "structured output 파싱 실패")
            ),
            reasoning_tokens=getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", None),
            finish_reason=response.choices[0].finish_reason,
        )


class JudgeAdapter:
    """채점용 어댑터. 비교 대상 3개 중 하나를 재사용하지 않는다(자기 채점 편향 방지) —
    실행 시점에 `JUDGE_MODEL` 환경변수로 어떤 모델을 쓸지 확정한다."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def judge(
        self,
        input_sentence: str,
        prior_hints: dict | None,
        expected_notes: str,
        candidate_output: dict | None,
    ) -> CandidateResult:
        user_prompt = JUDGE_USER_TEMPLATE.format(
            input_sentence=input_sentence,
            prior_hints_json=json.dumps(prior_hints, ensure_ascii=False),
            expected_notes=expected_notes,
            candidate_output_json=json.dumps(candidate_output, ensure_ascii=False),
        )
        start = time.monotonic()
        try:
            response = _client(self.model_name).chat.completions.parse(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=JudgeVerdict,
            )
        except Exception as exc:  # noqa: BLE001
            return CandidateResult(
                model_name=self.model_name,
                raw_text=None,
                parsed=None,
                latency_ms=(time.monotonic() - start) * 1000,
                prompt_tokens=None,
                completion_tokens=None,
                cost_krw=None,
                error=str(exc),
            )
        latency_ms = (time.monotonic() - start) * 1000

        message = response.choices[0].message
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        parsed_model = getattr(message, "parsed", None)

        return CandidateResult(
            model_name=self.model_name,
            raw_text=message.content,
            parsed=parsed_model.model_dump() if parsed_model is not None else None,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_krw=estimate_cost_krw(self.model_name, prompt_tokens, completion_tokens),
            error=(
                None
                if parsed_model is not None
                else (getattr(message, "refusal", None) or "structured output 파싱 실패")
            ),
        )
