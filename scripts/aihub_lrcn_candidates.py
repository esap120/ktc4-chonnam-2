#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2,<3", "numpy<2", "pycocotools", "typer"]
# ///
# How to run: uv run --with typer --with pycocotools python -m scripts.aihub_lrcn_candidates CACHE_DIR OUTPUT_JSON
"""Select cached sliding LRCN predictions after discarding oracle and truth fields."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import ClassVar, Final, Literal

import typer
from pydantic import BaseModel, ConfigDict

from scripts.aihub_hybrid_candidates import (
    Candidate,
    CandidateSet,
    ClipInput,
    ClipManifest,
    Event,
)

EVENTS: Final[tuple[Event, ...]] = (
    "SIGNAL",
    "CENTER_LINE_CROSSING",
    "SOLID_LINE_LANE_CHANGE",
)


class Prediction(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    mode: Literal["whole_clip", "oracle_event", "sliding_5sec"]
    interval: tuple[float, float]
    predicted: Event
    probabilities: tuple[float, float, float]


def select(
    clip: ClipInput, predictions: tuple[Prediction, ...]
) -> tuple[Candidate, ...]:
    selected: list[Candidate] = []
    for event in EVENTS:
        chosen: list[Candidate] = []
        eligible = (
            p
            for p in predictions
            if p.file == clip.file
            and p.mode == "sliding_5sec"
            and p.predicted == event
            and max(p.probabilities) >= 0.8
        )
        for p in sorted(eligible, key=lambda p: (-max(p.probabilities), p.interval[0])):
            start, end = p.interval
            if any(start < c.end_sec and c.start_sec < end for c in chosen):
                continue
            chosen.append(
                Candidate(
                    file=clip.file,
                    event=event,
                    start_sec=start,
                    end_sec=end,
                    peak_sec=(start + end) / 2,
                    score=max(p.probabilities),
                    track_id=None,
                    bbox_xyxy=None,
                    image_wh=None,
                    reason=f"sliding_5sec LRCN probabilities={p.probabilities}; no normal class",
                )
            )
            if len(chosen) == 2:
                break
        selected.extend(chosen)
    return tuple(selected)


def run(cache_dir: Path, output: Path) -> None:
    manifest = cache_dir / "manifest.json"
    clips = ClipManifest.model_validate_json(
        manifest.read_text(encoding="utf-8")
    ).videos
    path = cache_dir / "predictions/lrcn/classifications.jsonl"
    predictions = tuple(
        Prediction.model_validate_json(s)
        for s in path.read_text(encoding="utf-8").splitlines()
    )
    candidates = tuple(c for clip in clips for c in select(clip, predictions))
    result = CandidateSet(
        clips=clips,
        candidates=candidates,
        rules="Existing full-video 5sec / step2.5 LRCN predictions; score>=0.8, top2 non-overlapping per predicted type; no oracle, truth, spatial detector or vehicle hint; Fine padding4, 720p4fps low independent all3 types, one repeat.",
        cache_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        prediction_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest()},
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(
        f"Frozen {len(candidates)} candidates over {len(clips)} videos: {hashlib.sha256(output.read_bytes()).hexdigest()}"
    )


if __name__ == "__main__":
    typer.run(run)
