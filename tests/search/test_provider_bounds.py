"""Tests for GeminiProvider size caps, timeout wiring, and retry classification.

Uses a spying fake OpenAI client — never hits the network.
"""

import base64
import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest

from daesingo.search.config import GeminiSearchConfig
from daesingo.search.execution import DeadlineExceededError, RunDeadline
from daesingo.search.media import PreparedMedia
from daesingo.search.provider import (
    CoarseRequest,
    GeminiProvider,
    MediaSizeError,
    RequestSizeError,
)
from daesingo.search.runs import ContractRef
from daesingo.search.schemas import CoarseResponse
from daesingo.search.scope import VisualEventType
from daesingo.search.sources import ResolvedAnalysisSource

# ---------------------------------------------------------------------------
# Fake OpenAI SDK helpers
# ---------------------------------------------------------------------------


class _FakeApiError(Exception):
    status_code: int | None

    def __init__(self, message: str = "", *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeBadRequestError(_FakeApiError):
    pass


@dataclass(frozen=True, slots=True)
class _Msg:
    parsed: object


@dataclass(frozen=True, slots=True)
class _Choice:
    message: _Msg


@dataclass(frozen=True, slots=True)
class _Completion:
    choices: list[_Choice]
    usage: object | None = None


@dataclass
class _Completions:
    calls: list[dict[str, object]] = field(default_factory=list)
    raises: Exception | None = None

    def parse(self, **kwargs: object) -> _Completion:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return _Completion([_Choice(_Msg(CoarseResponse(candidates=())))])


@dataclass(frozen=True, slots=True)
class _Chat:
    completions: object  # accepts _Completions or any counting variant


@dataclass(frozen=True, slots=True)
class _FakeClient:
    chat: _Chat


def _make_openai_module(factory: Callable[..., object]) -> ModuleType:
    """Build a fake openai module with a given OpenAI factory callable."""
    mod = ModuleType("openai")
    setattr(mod, "OpenAI", factory)  # noqa: B010
    setattr(mod, "APIError", _FakeApiError)  # noqa: B010
    setattr(mod, "BadRequestError", _FakeBadRequestError)  # noqa: B010
    return mod


def _install_fake_openai(
    monkeypatch: pytest.MonkeyPatch,
    completions: _Completions,
) -> None:
    """Inject a fake openai module so GeminiProvider never hits the network."""
    mod = _make_openai_module(lambda **_kw: _FakeClient(_Chat(completions)))
    original = importlib.import_module

    def fake_import(name: str) -> ModuleType:
        return mod if name == "openai" else original(name)

    monkeypatch.setattr("daesingo.search.provider.importlib.import_module", fake_import)
    monkeypatch.setitem(sys.modules, "openai", mod)


def _make_media(path: Path, *, byte_size: int | None = None) -> PreparedMedia:
    data = path.read_bytes()
    return PreparedMedia(
        path=path,
        content_type="video/mp4",
        byte_size=byte_size if byte_size is not None else len(data),
        duration_sec=5.0,
        origin_start_sec=0.0,
        origin_end_sec=5.0,
    )


def _source() -> ResolvedAnalysisSource:
    return ResolvedAnalysisSource(
        ContractRef(kind="analysis_source", ref="s"), 12, "t", 1
    )


def _coarse_request(media: PreparedMedia, timeout_sec: float = 30.0) -> CoarseRequest:
    return CoarseRequest(
        _source(), (VisualEventType.SIGNAL,), media=media, timeout_sec=timeout_sec
    )


# ---------------------------------------------------------------------------
# Cap 1: raw media byte size
# ---------------------------------------------------------------------------


def test_media_too_large_raises_before_network_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MediaSizeError is raised and the network is never called."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    small_file = tmp_path / "clip.mp4"
    small_file.write_bytes(b"x" * 10)
    # Declare byte_size over cap — provider checks media.byte_size, not disk size
    media = PreparedMedia(
        path=small_file,
        content_type="video/mp4",
        byte_size=41 * 1024 * 1024,  # 41 MiB > cap of 40 MiB
        duration_sec=5.0,
        origin_start_sec=0.0,
        origin_end_sec=5.0,
    )
    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=0))

    with pytest.raises(MediaSizeError):
        _ = provider.search_coarse(_coarse_request(media))

    assert completions.calls == []  # network never invoked


def test_media_at_exact_cap_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """byte_size == cap is allowed."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    cap = 12 * 1024 * 1024
    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"x" * cap)
    media = _make_media(media_file, byte_size=cap)
    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=0))

    _ = provider.search_coarse(_coarse_request(media))
    assert len(completions.calls) == 1


# ---------------------------------------------------------------------------
# Cap 2: serialized request byte size
# ---------------------------------------------------------------------------


def test_request_too_large_raises_before_network_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RequestSizeError raised after media cap passes; network never called."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    tiny_file = tmp_path / "clip.mp4"
    tiny_file.write_bytes(b"x")
    media = _make_media(tiny_file, byte_size=1)

    config = GeminiSearchConfig(
        max_inline_media_bytes=12 * 1024 * 1024,
        max_inline_request_bytes=1,  # 1 byte — any real payload exceeds this
        max_retries=0,
    )
    provider = GeminiProvider("key", config)

    with pytest.raises(RequestSizeError):
        _ = provider.search_coarse(_coarse_request(media))

    assert completions.calls == []


# ---------------------------------------------------------------------------
# Timeout wiring: per-attempt timeout reaches the SDK call
# ---------------------------------------------------------------------------


def test_per_attempt_timeout_from_request_reaches_sdk_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exact timeout_sec from the request is forwarded as timeout= to parse()."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=0))

    _ = provider.search_coarse(_coarse_request(media, timeout_sec=42.5))

    assert completions.calls[0]["timeout"] == 42.5


def test_different_timeout_value_is_forwarded_correctly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second distinct timeout value also reaches parse() unchanged."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=0))

    _ = provider.search_coarse(_coarse_request(media, timeout_sec=5.0))
    assert completions.calls[0]["timeout"] == 5.0


# ---------------------------------------------------------------------------
# Only prepared bytes are encoded (never original source path content)
# ---------------------------------------------------------------------------


def test_provider_encodes_only_prepared_media_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The base64 payload comes from PreparedMedia.path, not any original source."""
    completions = _Completions()
    _install_fake_openai(monkeypatch, completions)

    prepared_file = tmp_path / "prepared.mp4"
    prepared_bytes = b"prepared-video-content"
    prepared_file.write_bytes(prepared_bytes)
    media = _make_media(prepared_file)

    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=0))
    _ = provider.search_coarse(_coarse_request(media))

    call = completions.calls[0]
    messages = call["messages"]
    assert isinstance(messages, list)
    content = messages[0]["content"]
    assert isinstance(content, list)
    file_part = next(p for p in content if p["type"] == "file")
    data_url = file_part["file"]["file_data"]
    assert isinstance(data_url, str)
    assert data_url.startswith("data:video/mp4;base64,")
    encoded_part = data_url.split(",", 1)[1]
    assert base64.b64decode(encoded_part) == prepared_bytes


# ---------------------------------------------------------------------------
# Non-retryable error: client called exactly once
# ---------------------------------------------------------------------------


def test_non_retryable_error_calls_client_exactly_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 400 BadRequestError is not retried — parse() is called exactly once."""
    bad_request = _FakeBadRequestError("bad schema", status_code=400)
    completions = _Completions(raises=bad_request)
    _install_fake_openai(monkeypatch, completions)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider("key", GeminiSearchConfig(max_retries=3))

    from daesingo.search.smoke_errors import ProviderPayloadError

    with pytest.raises(ProviderPayloadError):
        _ = provider.search_coarse(_coarse_request(media))

    assert len(completions.calls) == 1  # not retried


# ---------------------------------------------------------------------------
# Retry classification: status_code-based (via _FakeApiError.status_code)
# ---------------------------------------------------------------------------


def _make_counting_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    fail_with: _FakeApiError,
    max_retries: int,
) -> tuple[GeminiProvider, PreparedMedia, list[int]]:
    """Return (provider, media, call_counts) where call_counts is mutated on each parse()."""
    call_counts: list[int] = []

    class _CountingCompletions:
        def parse(self, **_kwargs: object) -> _Completion:
            call_counts.append(1)
            if len(call_counts) == 1:
                raise fail_with
            return _Completion([_Choice(_Msg(CoarseResponse(candidates=())))])

    counting = _CountingCompletions()
    mod = _make_openai_module(lambda **_kw: _FakeClient(_Chat(counting)))
    original = importlib.import_module

    def fake_import(name: str) -> ModuleType:
        return mod if name == "openai" else original(name)

    monkeypatch.setattr("daesingo.search.provider.importlib.import_module", fake_import)
    monkeypatch.setitem(sys.modules, "openai", mod)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider(
        "key", GeminiSearchConfig(max_retries=max_retries, retry_base_sec=0.0)
    )
    return provider, media, call_counts


def test_429_status_code_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An APIError with status_code=429 is retried."""
    provider, media, call_counts = _make_counting_provider(
        monkeypatch,
        tmp_path,
        fail_with=_FakeApiError("rate limited", status_code=429),
        max_retries=2,
    )
    _ = provider.search_coarse(_coarse_request(media))
    assert len(call_counts) == 2  # 1 failure + 1 success


def test_5xx_status_code_retries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An APIError with status_code=503 is retried."""
    provider, media, call_counts = _make_counting_provider(
        monkeypatch,
        tmp_path,
        fail_with=_FakeApiError("service unavailable", status_code=503),
        max_retries=2,
    )
    _ = provider.search_coarse(_coarse_request(media))
    assert len(call_counts) == 2


def test_4xx_auth_error_does_not_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An APIError with status_code=401 is NOT retried."""
    completions = _Completions(raises=_FakeApiError("unauthorized", status_code=401))
    _install_fake_openai(monkeypatch, completions)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider(
        "key", GeminiSearchConfig(max_retries=3, retry_base_sec=0.0)
    )

    from daesingo.search.smoke_errors import ProviderApiError

    with pytest.raises(ProviderApiError):
        _ = provider.search_coarse(_coarse_request(media))

    assert len(completions.calls) == 1


def test_unrelated_message_containing_500_does_not_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Error whose message contains '500' but has status_code=400 is NOT retried.

    This is the false-positive the brief tracked: bare string matching on "500"
    in the error message would have retried this as a server error.
    """
    err = _FakeApiError(
        "request contained 500 items which exceeded the limit", status_code=400
    )
    completions = _Completions(raises=err)
    _install_fake_openai(monkeypatch, completions)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    provider = GeminiProvider(
        "key", GeminiSearchConfig(max_retries=3, retry_base_sec=0.0)
    )

    from daesingo.search.smoke_errors import ProviderApiError

    with pytest.raises(ProviderApiError):
        _ = provider.search_coarse(_coarse_request(media))

    assert len(completions.calls) == 1  # not retried despite "500" in message


# ---------------------------------------------------------------------------
# Retry respects the run deadline (issue #149): the RunDeadline must reach
# call_with_retry so a retryable error is NOT retried past the time budget.
# ---------------------------------------------------------------------------


def test_retry_stops_when_run_deadline_exhausted_between_attempts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 429 is normally retried, but once the run budget is spent the provider
    must surface DeadlineExceededError instead of sleeping and retrying."""
    now = [0.0]

    def clock() -> float:
        return now[0]

    call_counts: list[int] = []

    class _ClockBurningCompletions:
        def parse(self, **_kwargs: object) -> _Completion:
            call_counts.append(1)
            now[0] += 0.2  # each attempt burns 200ms of budget
            raise _FakeApiError("rate limited", status_code=429)

    mod = _make_openai_module(
        lambda **_kw: _FakeClient(_Chat(_ClockBurningCompletions()))
    )
    original = importlib.import_module

    def fake_import(name: str) -> ModuleType:
        return mod if name == "openai" else original(name)

    monkeypatch.setattr("daesingo.search.provider.importlib.import_module", fake_import)
    monkeypatch.setitem(sys.modules, "openai", mod)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    media = _make_media(media_file)
    # base 5s backoff + 3 retries would run for seconds if the deadline were ignored.
    provider = GeminiProvider(
        "key", GeminiSearchConfig(max_retries=3, retry_base_sec=5.0)
    )

    deadline = RunDeadline(
        clock, budget_ms=100
    )  # 100ms budget; one attempt exhausts it
    request = CoarseRequest(
        _source(),
        (VisualEventType.SIGNAL,),
        media=media,
        timeout_sec=deadline.remaining_sec(),
        deadline=deadline,
    )

    with pytest.raises(DeadlineExceededError):
        _ = provider.search_coarse(request)

    assert len(call_counts) == 1  # exhausted after the first attempt → no retry


def test_retry_attempt_timeout_is_what_remains_of_run_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """30s budget, first attempt burns 20s then 429 → the retry gets ~10s, not 30s."""
    now = [0.0]
    timeouts: list[object] = []

    class _SlowThenOk:
        def parse(self, **kwargs: object) -> _Completion:
            timeouts.append(kwargs["timeout"])
            if len(timeouts) == 1:
                now[0] += 20.0
                raise _FakeApiError("rate limited", status_code=429)
            return _Completion([_Choice(_Msg(CoarseResponse(candidates=())))])

    mod = _make_openai_module(lambda **_kw: _FakeClient(_Chat(_SlowThenOk())))
    original = importlib.import_module

    def fake_import(name: str) -> ModuleType:
        return mod if name == "openai" else original(name)

    monkeypatch.setattr("daesingo.search.provider.importlib.import_module", fake_import)
    monkeypatch.setitem(sys.modules, "openai", mod)

    media_file = tmp_path / "clip.mp4"
    media_file.write_bytes(b"bytes")
    provider = GeminiProvider(
        "key", GeminiSearchConfig(max_retries=1, retry_base_sec=0.001)
    )
    deadline = RunDeadline(lambda: now[0], budget_ms=30_000)
    request = CoarseRequest(
        _source(),
        (VisualEventType.SIGNAL,),
        media=_make_media(media_file),
        timeout_sec=deadline.remaining_sec(),
        deadline=deadline,
    )

    _ = provider.search_coarse(request)

    assert timeouts == [30.0, 10.0]
