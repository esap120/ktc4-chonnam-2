#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["openai>=1.40,<3", "pydantic>=2,<3", "typer", "numpy<2", "pycocotools"]
# ///
# How to run: uv run --extra eval-gemini --extra test --with typer --with pycocotools python -m scripts.aihub_hybrid_score CANDIDATES_JSON FINE_JSONL TRUTH_MANIFEST OUTPUT_JSON

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import ClassVar

import typer
from pydantic import BaseModel, ConfigDict

from daesingo.search.visual import AssociationStatus, Verification
from scripts.aihub_hybrid_candidates import Candidate, CandidateSet
from scripts.aihub_hybrid_fine import FineResult


class Truth(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    event: str
    intervals: tuple[tuple[float, float], ...]


class TruthManifest(BaseModel):
    videos: tuple[Truth, ...]


def overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def accepted(row: FineResult) -> bool:
    response = row.response
    return bool(
        row.failure is None
        and response is not None
        and response.verification is Verification.OBSERVED
        and response.visual_event_type is not None
        and response.visual_event_type.value == row.candidate.event
        and response.target.association_status is AssociationStatus.MATCHED
        and response.target.match_with_hint is True
    )


class EventScore(BaseModel):
    file: str
    event: str
    interval: tuple[float, float]
    core_candidate_indices: tuple[int, ...]
    padded_candidate_indices: tuple[int, ...]
    observed_core_indices: tuple[int, ...]
    observed_padded_indices: tuple[int, ...]
    associated_padded_indices: tuple[int, ...]


def score_event(
    truth: Truth,
    interval: tuple[float, float],
    candidates: tuple[Candidate, ...],
    rows: tuple[FineResult, ...],
) -> EventScore:
    core = tuple(
        i
        for i, c in enumerate(candidates)
        if c.file == truth.file
        and c.event == truth.event
        and overlaps((c.start_sec, c.end_sec), interval)
    )
    padded = tuple(
        r.candidate_index
        for r in rows
        if r.candidate.file == truth.file
        and r.candidate.event == truth.event
        and overlaps(r.window, interval)
    )
    observed = {
        r.candidate_index
        for r in rows
        if r.failure is None
        and r.response is not None
        and r.response.verification is Verification.OBSERVED
        and r.response.visual_event_type is not None
        and r.response.visual_event_type.value == r.candidate.event
    }
    associated = {r.candidate_index for r in rows if accepted(r)}
    return EventScore(
        file=truth.file,
        event=truth.event,
        interval=interval,
        core_candidate_indices=core,
        padded_candidate_indices=padded,
        observed_core_indices=tuple(i for i in core if i in observed),
        observed_padded_indices=tuple(i for i in padded if i in observed),
        associated_padded_indices=tuple(i for i in padded if i in associated),
    )


class NormalScore(BaseModel):
    file: str
    fine_calls: int
    observed_indices: tuple[int, ...]
    accepted_indices: tuple[int, ...]
    failed_indices: tuple[int, ...]


class Report(BaseModel):
    candidates_sha256: str
    fine_sha256: str
    truth_manifest_sha256: str
    fine_calls: int
    model_counts: dict[str, int]
    verification_counts: dict[str, int]
    failure_counts: dict[str, int]
    candidate_core_events: int
    candidate_padded_events: int
    observed_core_events: int
    observed_padded_events: int
    associated_padded_events: int
    total_events: int
    normals: tuple[NormalScore, ...]
    events: tuple[EventScore, ...]
    input_tokens: int
    output_tokens: int
    summed_call_latency_sec: float
    total_fine_frames: int
    note: str


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
    assert {r.candidate_index for r in rows} == set(range(len(candidates.candidates)))
    assert all(
        r.candidates_sha256 == candidate_hash
        and r.candidate == candidates.candidates[r.candidate_index]
        for r in rows
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
    normals: list[NormalScore] = []
    for t in truths:
        if t.intervals:
            continue
        relevant = tuple(r for r in rows if r.candidate.file == t.file)
        normals.append(
            NormalScore(
                file=t.file,
                fine_calls=len(relevant),
                observed_indices=tuple(
                    r.candidate_index
                    for r in relevant
                    if r.response is not None
                    and r.response.verification is Verification.OBSERVED
                ),
                accepted_indices=tuple(
                    r.candidate_index for r in relevant if accepted(r)
                ),
                failed_indices=tuple(
                    r.candidate_index for r in relevant if r.failure is not None
                ),
            )
        )
    result = Report(
        candidates_sha256=candidate_hash,
        fine_sha256=hashlib.sha256(fine_jsonl.read_bytes()).hexdigest(),
        truth_manifest_sha256=hashlib.sha256(truth_manifest.read_bytes()).hexdigest(),
        fine_calls=len(rows),
        model_counts=dict(Counter(r.model or "FAILED" for r in rows)),
        verification_counts=dict(
            Counter(
                r.response.verification.value if r.response else "FAILED" for r in rows
            )
        ),
        failure_counts=dict(Counter(r.failure for r in rows if r.failure is not None)),
        candidate_core_events=sum(bool(e.core_candidate_indices) for e in events),
        candidate_padded_events=sum(bool(e.padded_candidate_indices) for e in events),
        observed_core_events=sum(bool(e.observed_core_indices) for e in events),
        observed_padded_events=sum(bool(e.observed_padded_indices) for e in events),
        associated_padded_events=sum(bool(e.associated_padded_indices) for e in events),
        total_events=len(events),
        normals=tuple(normals),
        events=events,
        input_tokens=sum(r.input_tokens or 0 for r in rows),
        output_tokens=sum(r.output_tokens or 0 for r in rows),
        summed_call_latency_sec=sum(r.latency_sec for r in rows),
        total_fine_frames=sum(r.frames for r in rows),
        note="Window overlap plus Fine label is a diagnostic proxy: it does not verify violation moment or ground-truth target identity. All three event types, 1 repeat; candidate generation used no truth. Associated metric additionally requires MATCHED and match_with_hint=True. No automatic retry; failures are not correct rejections.",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    typer.run(run)
