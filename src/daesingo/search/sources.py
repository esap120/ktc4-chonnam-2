from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, override

from .errors import CandidateSourceMismatchError
from .media import MediaInput
from .runs import CandidateEvent, ContractRef
from .scope import AnalysisScope

# ---------------------------------------------------------------------------
# Typed errors for resolver operations
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnalysisSourceNotFoundError(Exception):
    ref: str

    @override
    def __str__(self) -> str:
        return f"analysis source not found: {self.ref!r}"


@dataclass(frozen=True, slots=True)
class AnalysisSourceUnavailableError(Exception):
    ref: str
    detail: str = ""

    @override
    def __str__(self) -> str:
        return f"analysis source unavailable: {self.ref!r}" + (
            f" — {self.detail}" if self.detail else ""
        )


@dataclass(frozen=True, slots=True)
class AnalysisSourceTemporaryFailureError(Exception):
    ref: str
    detail: str = ""

    @override
    def __str__(self) -> str:
        return f"analysis source temporary failure: {self.ref!r}" + (
            f" — {self.detail}" if self.detail else ""
        )


# ---------------------------------------------------------------------------
# Metadata-only resolved source (NO path, URL, or credentials)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedAnalysisSource:
    source_ref: ContractRef
    duration_sec: float
    timeline_id: str
    timeline_revision: int = 1
    # 이 입력의 0초가 Timeline의 몇 초인가(AnalysisSource.timeline_range.start_sec).
    # Coarse 후보는 이만큼 더해 Timeline 좌표로, Fine은 빼서 입력 좌표로 쓴다(#252).
    timeline_start_sec: float = 0.0

    @property
    def source_id(self) -> str:
        """Convenience alias — resolves to the ref string."""
        return self.source_ref.ref


# ---------------------------------------------------------------------------
# CandidateSourceLink (unchanged behaviour)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateSourceLink:
    source_ref: ContractRef
    candidate: CandidateEvent

    def validate(self, source: ResolvedAnalysisSource) -> None:
        candidate_span = self.candidate.span
        matches_source = (
            self.source_ref.kind == "analysis_source"
            and source.source_ref == self.source_ref
            and candidate_span.timeline_id == source.timeline_id
            and candidate_span.timeline_revision == source.timeline_revision
        )
        if not matches_source:
            raise CandidateSourceMismatchError(
                source_ref=self.source_ref,
                candidate_id=self.candidate.candidate_id,
                candidate_timeline_id=candidate_span.timeline_id,
                candidate_timeline_revision=candidate_span.timeline_revision,
                source_timeline_id=source.timeline_id,
                source_timeline_revision=source.timeline_revision,
            )


# ---------------------------------------------------------------------------
# Resolver protocol
# ---------------------------------------------------------------------------


class AnalysisSourceResolver(Protocol):
    def resolve(self, scope: AnalysisScope) -> tuple[ResolvedAnalysisSource, ...]: ...

    def resolve_reference(self, input_ref: ContractRef) -> ResolvedAnalysisSource: ...

    def open_source(self, ref: ContractRef) -> AbstractContextManager[MediaInput]: ...


# ---------------------------------------------------------------------------
# StaticAnalysisSourceResolver (test / fixture helper)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StaticAnalysisSourceResolver:
    sources_by_scope: dict[str, tuple[ResolvedAnalysisSource, ...]]
    sources_by_ref: dict[str, ResolvedAnalysisSource]

    def resolve(self, scope: AnalysisScope) -> tuple[ResolvedAnalysisSource, ...]:
        try:
            return self.sources_by_scope[scope.scope_id]
        except KeyError as error:
            raise LookupError(
                f"no analysis source for scope {scope.scope_id!r}"
            ) from error

    def resolve_reference(self, input_ref: ContractRef) -> ResolvedAnalysisSource:
        try:
            return self.sources_by_ref[input_ref.ref]
        except KeyError as error:
            raise LookupError(
                f"no analysis source for ref {input_ref.ref!r}"
            ) from error

    def open_source(self, ref: ContractRef) -> AbstractContextManager[MediaInput]:
        _ = ref
        raise NotImplementedError(
            "StaticAnalysisSourceResolver does not support open_source; use LocalAnalysisSourceResolver or RecordingAnalysisSourceResolver"
        )


# ---------------------------------------------------------------------------
# LocalAnalysisSourceResolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LocalAnalysisSourceResolver:
    """Resolves analysis sources from local files.

    The Path lives ONLY here — never on ResolvedAnalysisSource.
    """

    sources_by_scope: dict[str, tuple[ResolvedAnalysisSource, ...]]
    sources_by_ref: dict[str, ResolvedAnalysisSource]
    paths_by_ref: dict[str, Path]

    def resolve(self, scope: AnalysisScope) -> tuple[ResolvedAnalysisSource, ...]:
        try:
            return self.sources_by_scope[scope.scope_id]
        except KeyError as error:
            raise LookupError(
                f"no analysis source for scope {scope.scope_id!r}"
            ) from error

    def resolve_reference(self, input_ref: ContractRef) -> ResolvedAnalysisSource:
        try:
            return self.sources_by_ref[input_ref.ref]
        except KeyError as error:
            raise LookupError(
                f"no analysis source for ref {input_ref.ref!r}"
            ) from error

    @contextmanager
    def open_source(self, ref: ContractRef) -> Generator[MediaInput]:
        """Open the local file and yield MediaInput; close on exit."""
        path = self.paths_by_ref.get(ref.ref)
        if path is None:
            raise AnalysisSourceNotFoundError(ref.ref)
        byte_size = path.stat().st_size
        with path.open("rb") as f:
            yield MediaInput(
                stream=f, content_type="video/mp4", declared_byte_size=byte_size
            )


# ---------------------------------------------------------------------------
# RecordingAnalysisSourceGateway — narrow protocol (do NOT import recording.**)
# ---------------------------------------------------------------------------


class _OpenedSource(Protocol):
    """Structural protocol matching Recording's OpenedAnalysisSource shape."""

    stream: BinaryIO
    content_type: str
    byte_size: int


class RecordingAnalysisSourceGateway(Protocol):
    """Narrow gateway to Recording — only the one method Search needs."""

    def open_analysis_source(self, analysis_source_ref: str) -> _OpenedSource: ...


# ---------------------------------------------------------------------------
# RecordingAnalysisSourceResolver
# ---------------------------------------------------------------------------

_RECORDING_ERROR_MAP: dict[
    str,
    type[AnalysisSourceUnavailableError | AnalysisSourceTemporaryFailureError],
] = {
    "UNAVAILABLE": AnalysisSourceUnavailableError,
    "TEMPORARY_FAILURE": AnalysisSourceTemporaryFailureError,
    # Defensive: UNSUPPORTED_MEDIA is documented but not raised by recording/service.py today.
    # ponytail: mapping included defensively; exercise only via fake gateway in tests.
    "UNSUPPORTED_MEDIA": AnalysisSourceUnavailableError,
}


@dataclass(frozen=True, slots=True)
class SourceMeta:
    duration_sec: float
    timeline_id: str
    timeline_revision: int
    timeline_start_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class RecordingAnalysisSourceResolver:
    """Resolves analysis sources via the Recording gateway.

    ``scope_sources``: maps scope_id → tuple of analysis_source ContractRefs.
    ``ref_metadata``: maps ref string → SourceMeta (duration_sec, timeline_id, timeline_revision).
    ``gateway``: narrow RecordingAnalysisSourceGateway.

    Refs are resolved ONLY from the explicit mapping — never inferred from
    scope/timeline/filesystem.
    """

    scope_sources: dict[str, tuple[ContractRef, ...]]
    ref_metadata: dict[str, SourceMeta]
    gateway: RecordingAnalysisSourceGateway

    def _resolved(self, ref: ContractRef) -> ResolvedAnalysisSource:
        meta = self.ref_metadata.get(ref.ref)
        if meta is None:
            raise AnalysisSourceNotFoundError(ref.ref)
        return ResolvedAnalysisSource(
            source_ref=ref,
            duration_sec=meta.duration_sec,
            timeline_id=meta.timeline_id,
            timeline_revision=meta.timeline_revision,
            timeline_start_sec=meta.timeline_start_sec,
        )

    def resolve(self, scope: AnalysisScope) -> tuple[ResolvedAnalysisSource, ...]:
        refs = self.scope_sources.get(scope.scope_id)
        if refs is None:
            raise LookupError(f"no analysis source for scope {scope.scope_id!r}")
        return tuple(self._resolved(ref) for ref in refs)

    def resolve_reference(self, input_ref: ContractRef) -> ResolvedAnalysisSource:
        return self._resolved(input_ref)

    @contextmanager
    def open_source(self, ref: ContractRef) -> Generator[MediaInput]:
        """Delegate to gateway, wrap as MediaInput, close stream on exit."""
        from daesingo.recording.errors import RecordingCapabilityError

        try:
            opened = self.gateway.open_analysis_source(ref.ref)
        except RecordingCapabilityError as exc:
            if exc.code == "NOT_FOUND":
                raise AnalysisSourceNotFoundError(ref.ref) from exc
            error_cls = _RECORDING_ERROR_MAP.get(
                exc.code, AnalysisSourceTemporaryFailureError
            )
            raise error_cls(ref.ref, str(exc)) from exc
        try:
            yield MediaInput(
                stream=opened.stream,
                content_type=opened.content_type,
                declared_byte_size=opened.byte_size,
            )
        finally:
            opened.stream.close()
