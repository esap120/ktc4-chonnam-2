"""자연어 단서 구조화(#210) — 상태 분류 · 실패 분류 · 텍스트 호출 배선."""

import importlib
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import BaseModel, ValidationError

from daesingo.search import IntentFailureKind, IntentHintStatus
from daesingo.search.config import GeminiSearchConfig
from daesingo.search.execution import DeadlineExceededError
from daesingo.search.intent import (
    INTENT_SYSTEM_PROMPT,
    IntentHintExtraction,
    IntentHintExtractor,
    intent_config_from_dotenv,
)
from daesingo.search.provider import GeminiProvider, ProviderResult, TextInvocation
from daesingo.search.smoke_errors import ProviderApiError, ProviderPayloadError
from daesingo.search.usage import ProviderUsage


def _extraction(**overrides: object) -> IntentHintExtraction:
    values: dict[str, object] = {
        "time_hint": None,
        "vehicle_hint": None,
        "situation_hint": None,
        "location_hint": None,
        "correction_target": None,
        "confidence": "high",
        "reasoning": "근거",
    }
    values.update(overrides)
    return IntentHintExtraction.model_validate(values)


@dataclass
class _FakeProvider:
    response: IntentHintExtraction | None = None
    raises: Exception | None = None
    calls: list[TextInvocation[BaseModel]] = field(default_factory=list)

    def invoke_text[ResponseT: BaseModel](
        self, request: TextInvocation[ResponseT]
    ) -> ProviderResult[ResponseT]:
        self.calls.append(request)  # pyright: ignore[reportArgumentType]
        if self.raises is not None:
            raise self.raises
        assert self.response is not None
        return ProviderResult(
            self.response,  # pyright: ignore[reportArgumentType]
            ProviderUsage(100, 20, 0, 120),
            latency_ms=3900,
        )


def _extractor(provider: _FakeProvider) -> IntentHintExtractor:
    return IntentHintExtractor(provider, GeminiSearchConfig())


def test_ok_maps_fields_and_usage_without_reasoning() -> None:
    provider = _FakeProvider(
        _extraction(time_hint="어제 저녁", vehicle_hint="흰색 SUV", confidence="low")
    )

    result = _extractor(provider).extract(
        "어제 저녁 흰색 SUV가 끼어들었어요", case_id="c1"
    )

    assert result.status is IntentHintStatus.OK
    assert (result.time_hint, result.vehicle_hint) == ("어제 저녁", "흰색 SUV")
    assert result.situation_hint is None
    assert result.confidence == "low"
    assert result.failure_kind is None
    assert not hasattr(result, "reasoning")
    assert result.usage is not None
    assert result.usage.case_id == "c1"
    assert result.usage.prompt_version == "intent-v3"
    assert result.usage.latency_ms == 3900


def test_user_prompt_carries_text_and_prior_hints() -> None:
    provider = _FakeProvider(_extraction(time_hint="19시"))

    _ = _extractor(provider).extract(
        "시간 그거 말고 19시였어요",
        case_id="c1",
        prior_hints={"vehicle_hint": "흰색 SUV"},
    )

    sent = provider.calls[0]
    assert sent.system_prompt == INTENT_SYSTEM_PROMPT.text
    assert '"vehicle_hint": "흰색 SUV"' in sent.user_prompt
    assert '"시간 그거 말고 19시였어요"' in sent.user_prompt


def test_all_hints_empty_is_abstained_with_confidence_kept() -> None:
    provider = _FakeProvider(_extraction(confidence="low"))

    result = _extractor(provider).extract("잘 모르겠어요", case_id="c1")

    assert result.status is IntentHintStatus.ABSTAINED
    assert result.confidence == "low"
    assert result.usage is not None


@pytest.mark.parametrize("text", ["", "   \n"])
def test_blank_text_abstains_without_provider_call(text: str) -> None:
    provider = _FakeProvider()

    result = _extractor(provider).extract(text, case_id="c1")

    assert result.status is IntentHintStatus.ABSTAINED
    assert result.usage is None
    assert provider.calls == []


def _caused(error: Exception, cause: Exception) -> Exception:
    error.__cause__ = cause
    return error


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(status_code)
        self.status_code = status_code


def _status_error(status: int) -> Exception:
    return _StatusError(status)


def _validation_error() -> ValidationError:
    try:
        _ = IntentHintExtraction.model_validate({})
    except ValidationError as error:
        return error
    raise AssertionError("unreachable")


@pytest.mark.parametrize(
    ("raised", "kind"),
    [
        (DeadlineExceededError("budget"), IntentFailureKind.DEADLINE_EXCEEDED),
        (
            _caused(ProviderApiError("x"), _status_error(401)),
            IntentFailureKind.CONFIG_ERROR,
        ),
        (
            _caused(ProviderPayloadError("x"), _status_error(404)),
            IntentFailureKind.CONFIG_ERROR,
        ),
        (
            _caused(ProviderPayloadError("x"), _validation_error()),
            IntentFailureKind.RESPONSE_INVALID,
        ),
        (ProviderPayloadError("no parsed content"), IntentFailureKind.RESPONSE_INVALID),
        (
            _caused(ProviderPayloadError("x"), _status_error(400)),
            IntentFailureKind.PROVIDER_ERROR,
        ),
        (
            _caused(ProviderApiError("x"), _status_error(503)),
            IntentFailureKind.PROVIDER_ERROR,
        ),
        (RuntimeError("unexpected"), IntentFailureKind.PROVIDER_ERROR),
    ],
)
def test_failures_never_raise_and_are_classified(
    raised: Exception, kind: IntentFailureKind
) -> None:
    result = _extractor(_FakeProvider(raises=raised)).extract("문장", case_id="c1")

    assert result.status is IntentHintStatus.FAILED
    assert result.failure_kind is kind
    assert result.usage is None
    assert result.time_hint is None


def test_slow_call_hitting_the_cap_is_deadline_exceeded() -> None:
    clock = iter([0.0, 61.0, 61.0])
    provider = _FakeProvider(
        raises=_caused(ProviderApiError("timed out"), RuntimeError())
    )
    extractor = IntentHintExtractor(provider, GeminiSearchConfig(), lambda: next(clock))

    result = extractor.extract("문장", case_id="c1")

    assert result.failure_kind is IntentFailureKind.DEADLINE_EXCEEDED


def test_truncated_response_is_response_invalid() -> None:
    from openai import LengthFinishReasonError

    error = LengthFinishReasonError.__new__(LengthFinishReasonError)

    result = _extractor(_FakeProvider(raises=error)).extract("문장", case_id="c1")

    assert result.failure_kind is IntentFailureKind.RESPONSE_INVALID


@pytest.mark.parametrize("timeout_sec", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(timeout_sec: float) -> None:
    with pytest.raises(ValueError):
        _ = _extractor(_FakeProvider()).extract(
            "문장", case_id="c1", timeout_sec=timeout_sec
        )


def test_intent_model_key_is_separate_from_search_model() -> None:
    env = {
        "DAESINGO_GEMINI_MODEL": "coarse-model",
        "DAESINGO_INTENT_MODEL": "intent-model",
    }

    assert intent_config_from_dotenv(env).model == "intent-model"
    assert intent_config_from_dotenv(
        {"DAESINGO_GEMINI_MODEL": "coarse-model"}
    ).model == ("gemini-3.8-flash")


def test_gemini_provider_text_call_sends_system_and_user_without_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def parse(**kwargs: object) -> object:
        calls.append(kwargs)
        message = SimpleNamespace(parsed=_extraction(time_hint="어제"))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )
    mod = ModuleType("openai")
    setattr(mod, "OpenAI", lambda **_kw: client)  # noqa: B010
    setattr(mod, "APIError", type("APIError", (Exception,), {}))  # noqa: B010
    setattr(mod, "BadRequestError", type("BadRequestError", (Exception,), {}))  # noqa: B010
    original = importlib.import_module
    monkeypatch.setattr(
        "daesingo.search.provider.importlib.import_module",
        lambda name: mod if name == "openai" else original(name),
    )
    monkeypatch.setitem(sys.modules, "openai", mod)
    config = GeminiSearchConfig(model="intent-model", max_retries=0)

    result = IntentHintExtractor(GeminiProvider("key", config), config).extract(
        "어제 그랬어요", case_id="c1"
    )

    assert result.status is IntentHintStatus.OK
    sent = calls[0]
    assert sent["model"] == "intent-model"
    assert "reasoning_effort" not in sent
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]  # pyright: ignore[reportGeneralTypeIssues]
    assert 0 < sent["timeout"] <= 60.0  # pyright: ignore[reportOperatorIssue]
