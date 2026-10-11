#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2,<3", "openai>=1.40,<3", "numpy<2", "pycocotools", "typer"]
# ///
# How to run: uv run --extra eval-gemini --with typer --with pycocotools python -m scripts.aihub_lrcn_score CANDIDATES FINE TRUTH OUTPUT
"""Score independent Fine types, including corrections of the LRCN prediction."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import ClassVar

import typer
from pydantic import BaseModel, ConfigDict

from daesingo.search.visual import Verification
from scripts.aihub_hybrid_candidates import Candidate, CandidateSet
from scripts.aihub_hybrid_fine import FineResult
from scripts.aihub_hybrid_score import Truth, TruthManifest, overlaps


class EventScore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    event: str
    interval: tuple[float, float]
    selected_core: tuple[int, ...]
    predicted_type_core: tuple[int, ...]
    selected_padded: tuple[int, ...]
    observed_core: tuple[int, ...]
    observed_padded: tuple[int, ...]
    corrected_type_padded: tuple[int, ...]


class NormalScore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    calls: int
    observed: tuple[int, ...]
    failed: tuple[int, ...]


class Report(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    candidates_sha256: str
    fine_sha256: str
    truth_sha256: str
    calls: int
    model_counts: dict[str, int]
    verification_counts: dict[str, int]
    failure_counts: dict[str, int]
    events: tuple[EventScore, ...]
    normals: tuple[NormalScore, ...]
    selected_core_events: int
    predicted_type_core_events: int
    selected_padded_events: int
    observed_core_events: int
    observed_padded_events: int
    corrected_type_padded_events: int
    input_tokens: int
    output_tokens: int
    frames: int
    call_latency_sec: float
    note: str


def observed_as(row: FineResult, event: str) -> bool:
    response = row.response
    return bool(
        row.failure is None
        and response is not None
        and response.verification is Verification.OBSERVED
        and response.visual_event_type is not None
        and response.visual_event_type.value == event
    )


def score_event(
    truth: Truth,
    interval: tuple[float, float],
    candidates: tuple[Candidate, ...],
    rows: tuple[FineResult, ...],
) -> EventScore:
    core = tuple(
        i
        for i, c in enumerate(candidates)
        if c.file == truth.file and overlaps((c.start_sec, c.end_sec), interval)
    )
    padded = tuple(
        r.candidate_index
        for r in rows
        if r.candidate.file == truth.file and overlaps(r.window, interval)
    )
    observed = {r.candidate_index for r in rows if observed_as(r, truth.event)}
    return EventScore(
        file=truth.file,
        event=truth.event,
        interval=interval,
        selected_core=core,
        predicted_type_core=tuple(
            i for i in core if candidates[i].event == truth.event
        ),
        selected_padded=padded,
        observed_core=tuple(i for i in core if i in observed),
        observed_padded=tuple(i for i in padded if i in observed),
        corrected_type_padded=tuple(
            i for i in padded if i in observed and candidates[i].event != truth.event
        ),
    )


def run(
    candidates_json: Path, fine_jsonl: Path, truth_manifest: Path, output: Path
) -> None:
    candidates = CandidateSet.model_validate_json(
        candidates_json.read_text(encoding="utf-8")
    )
    rows = tuple(
        FineResult.model_validate_json(s)
        for s in fine_jsonl.read_text(encoding="utf-8").splitlines()
    )
    candidate_hash = hashlib.sha256(candidates_json.read_bytes()).hexdigest()
    assert len(rows) == len(candidates.candidates)
    assert {r.candidate_index for r in rows} == set(range(len(rows)))
    assert all(
        r.candidates_sha256 == candidate_hash
        and r.candidate == candidates.candidates[r.candidate_index]
        for r in rows
    )
    assert all(
        r.candidate.bbox_xyxy is None and r.candidate.track_id is None for r in rows
    )
    truths = TruthManifest.model_validate_json(
        truth_manifest.read_text(encoding="utf-8")
    ).videos
    assert {t.file for t in truths} == {c.file for c in candidates.clips}
    events = tuple(
        score_event(t, interval, candidates.candidates, rows)
        for t in truths
        for interval in t.intervals
    )
    normals = tuple(
        NormalScore(
            file=t.file,
            calls=sum(r.candidate.file == t.file for r in rows),
            observed=tuple(
                r.candidate_index
                for r in rows
                if r.candidate.file == t.file
                and r.response is not None
                and r.response.verification is Verification.OBSERVED
            ),
            failed=tuple(
                r.candidate_index
                for r in rows
                if r.candidate.file == t.file and r.failure is not None
            ),
        )
        for t in truths
        if not t.intervals
    )
    result = Report(
        candidates_sha256=candidate_hash,
        fine_sha256=hashlib.sha256(fine_jsonl.read_bytes()).hexdigest(),
        truth_sha256=hashlib.sha256(truth_manifest.read_bytes()).hexdigest(),
        calls=len(rows),
        model_counts=dict(Counter(r.model or "FAILED" for r in rows)),
        verification_counts=dict(
            Counter(
                r.response.verification.value if r.response else "FAILED" for r in rows
            )
        ),
        failure_counts=dict(Counter(r.failure for r in rows if r.failure is not None)),
        events=events,
        normals=normals,
        selected_core_events=sum(bool(e.selected_core) for e in events),
        predicted_type_core_events=sum(bool(e.predicted_type_core) for e in events),
        selected_padded_events=sum(bool(e.selected_padded) for e in events),
        observed_core_events=sum(bool(e.observed_core) for e in events),
        observed_padded_events=sum(bool(e.observed_padded) for e in events),
        corrected_type_padded_events=sum(bool(e.corrected_type_padded) for e in events),
        input_tokens=sum(r.input_tokens or 0 for r in rows),
        output_tokens=sum(r.output_tokens or 0 for r in rows),
        frames=sum(r.frames for r in rows),
        call_latency_sec=round(sum(r.latency_sec for r in rows), 3),
        note="Single repeat, known development videos. Coverage accepts any candidate type because Fine independently examines all3 types. Fine success is matching reported type plus window overlap, not verified violation time or target identity. No vehicle hint/association success claim. One event per response. Failed calls are not correct rejections.",
    )
    _ = output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    typer.run(run)
