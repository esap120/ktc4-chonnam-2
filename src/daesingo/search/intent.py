"""자연어 단서 구조화 — 사용자 원문을 LLM 1회로 구조화한다(#210).

search는 프롬프트 · 스키마 · provider 호출 · 실패 분류를 맡고, 결과를 `case.hints`로
옮기는 매핑과 실패 시 처리는 case가 맡는다. 모델 선정은 case 결정이다
(`docs/modules/case/decisions/intent-llm-model-selection.md`).
"""

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Final, Literal, Protocol

from pydantic import BaseModel

from daesingo.common import load_env_file

from .config import GeminiSearchConfig
from .execution import DeadlineExceededError, RunDeadline
from .ledger import UsageRecord
from .prompts import load_prompt
from .provider import GeminiProvider, ProviderResult, TextInvocation
from .smoke_errors import ProviderPayloadError

INTENT_SYSTEM_PROMPT: Final = load_prompt("intent-v3")
INTENT_USER_PROMPT: Final = load_prompt("intent-user-v1")

# Coarse · Fine 모델(DAESINGO_GEMINI_MODEL)을 바꿔도 intent 모델은 따로 남는다.
INTENT_MODEL_ENV: Final = "DAESINGO_INTENT_MODEL"
DEFAULT_INTENT_MODEL: Final = "gemini-3.8-flash"
# 재시도 포함 전체 상한. 실측 평균 3.9초 × 최대 4회 시도 + 재시도 대기 5+10+20초가 들어간다.
DEFAULT_INTENT_TIMEOUT_SEC: Final = 60.0

# 인증 · 접근 실패는 재시도해도 같으므로 설정 오류로 본다(모델 ID 오타 포함).
_CONFIG_ERROR_STATUS: Final = frozenset({401, 403, 404})


class IntentHintExtraction(BaseModel):
    """모델 structured output 스키마. case 실험 하네스가 이 정의를 import한다.

    `reasoning`은 모델이 판단 근거를 쓰게 두는 필드라 결과(`IntentHintResult`)에는 싣지 않는다.
    """

    time_hint: str | None
    vehicle_hint: str | None
    situation_hint: str | None
    location_hint: str | None
    correction_target: str | None
    confidence: Literal["high", "low"]
    reasoning: str


class IntentHintStatus(StrEnum):
    OK = "OK"  # 구조화 성공. 일부 필드는 비어 있을 수 있다.
    ABSTAINED = (
        "ABSTAINED"  # 호출 · 파싱은 됐지만 단서 4개가 모두 비었다(빈 원문 포함).
    )
    FAILED = "FAILED"


class IntentFailureKind(StrEnum):
    PROVIDER_ERROR = "PROVIDER_ERROR"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    CONFIG_ERROR = "CONFIG_ERROR"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"


@dataclass(frozen=True, slots=True)
class IntentHintResult:
    status: IntentHintStatus
    time_hint: str | None = None
    vehicle_hint: str | None = None
    situation_hint: str | None = None
    location_hint: str | None = None
    correction_target: str | None = None
    confidence: Literal["high", "low"] | None = None
    failure_kind: IntentFailureKind | None = None
    # provider 호출이 성공했을 때만 있다. 원문 응답은 담지 않는다.
    usage: UsageRecord | None = None


class TextStructuredProvider(Protocol):
    def invoke_text[ResponseT: BaseModel](
        self, request: TextInvocation[ResponseT]
    ) -> ProviderResult[ResponseT]: ...


@dataclass(slots=True)
class IntentHintExtractor:
    provider: TextStructuredProvider
    config: GeminiSearchConfig
    monotonic: Callable[[], float] = field(default=time.monotonic)

    def extract(
        self,
        text: str,
        *,
        case_id: str,
        prior_hints: Mapping[str, str | None] | None = None,
        timeout_sec: float = DEFAULT_INTENT_TIMEOUT_SEC,
    ) -> IntentHintResult:
        """Worker에서 1회 부른다. provider 실패는 던지지 않고 `FAILED`로 돌려준다.

        인자 오류(`timeout_sec`가 양수가 아님)만 `ValueError`로 던진다.
        """
        if not math.isfinite(timeout_sec) or timeout_sec <= 0:
            raise ValueError("timeout_sec must be finite and positive")
        if not text.strip():
            return IntentHintResult(IntentHintStatus.ABSTAINED)

        invocation = TextInvocation(
            system_prompt=INTENT_SYSTEM_PROMPT.text,
            user_prompt=INTENT_USER_PROMPT.render(
                prior_hints_json=json.dumps(prior_hints, ensure_ascii=False),
                input_sentence=text,
            ),
            response_model=IntentHintExtraction,
            deadline=RunDeadline(self.monotonic, round(timeout_sec * 1000)),
        )
        try:
            result = self.provider.invoke_text(invocation)
        except Exception as error:  # noqa: BLE001 — 어떤 실패도 intake를 막지 않는다
            return IntentHintResult(
                IntentHintStatus.FAILED,
                failure_kind=_failure_kind(error, invocation.deadline),
            )

        parsed = result.response
        hints = (
            parsed.time_hint,
            parsed.vehicle_hint,
            parsed.situation_hint,
            parsed.location_hint,
        )
        status = (
            IntentHintStatus.ABSTAINED
            if all(hint is None for hint in hints)
            else IntentHintStatus.OK
        )
        return IntentHintResult(
            status,
            *hints,
            correction_target=parsed.correction_target,
            confidence=parsed.confidence,
            usage=self._usage_record(case_id, result),
        )

    def _usage_record(
        self, case_id: str, result: ProviderResult[IntentHintExtraction]
    ) -> UsageRecord:
        return UsageRecord(
            case_id=case_id,
            model=self.config.model,
            prompt_version=INTENT_SYSTEM_PROMPT.version,
            prompt_fingerprint=INTENT_SYSTEM_PROMPT.fingerprint,
            config_version=self.config.version,
            processed_duration_sec=0.0,
            latency_ms=result.latency_ms,
            usage=result.usage,
            # ponytail: 단가는 Coarse · Fine과 같은 DAESINGO_GEMINI_*_USD_PER_MILLION을 쓴다.
            # intent 모델을 다른 모델로 바꾸면 intent 전용 단가 키를 따로 둔다.
            cost_usd=result.usage.cost_with_rates(
                self.config.input_usd_per_million,
                self.config.output_usd_per_million,
            ),
        )


def _failure_kind(error: Exception, deadline: RunDeadline) -> IntentFailureKind:
    from openai import ContentFilterFinishReasonError, LengthFinishReasonError

    # 한 번의 느린 호출이 상한에 걸리면 SDK timeout(APIError)으로 끝나므로 남은 예산으로 판단한다.
    if isinstance(error, DeadlineExceededError) or deadline.remaining_ms() <= 0:
        return IntentFailureKind.DEADLINE_EXCEEDED
    # 호출은 됐지만 응답이 잘리거나 걸러져 쓸 수 없다.
    if isinstance(error, LengthFinishReasonError | ContentFilterFinishReasonError):
        return IntentFailureKind.RESPONSE_INVALID
    status = getattr(error.__cause__, "status_code", None)
    if status in _CONFIG_ERROR_STATUS:
        return IntentFailureKind.CONFIG_ERROR
    if isinstance(error, ProviderPayloadError) and status is None:
        return IntentFailureKind.RESPONSE_INVALID
    return IntentFailureKind.PROVIDER_ERROR


def intent_config_from_dotenv(
    env: Mapping[str, str] | None = None,
) -> GeminiSearchConfig:
    """인증 · base URL · 재시도는 Search 설정을 공유하고 모델만 별도 키로 바꾼다."""
    if env is None:
        env = load_env_file()
    model = env.get(INTENT_MODEL_ENV, "").strip() or DEFAULT_INTENT_MODEL
    return replace(GeminiSearchConfig.from_dotenv(env), model=model)


def build_intent_hint_extractor(
    api_key: str,
    config: GeminiSearchConfig | None = None,
) -> IntentHintExtractor:
    selected = config or intent_config_from_dotenv()
    return IntentHintExtractor(GeminiProvider(api_key, selected), selected)
