#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy<2", "opencv-python==4.10.0.84", "pycocotools", "pydantic>=2,<3", "typer"]
# ///
# How to run: uv run scripts/aihub_hybrid_candidates.py CACHE_DIR OUTPUT_JSON
"""Truth-blind, bounded candidate proposals from cached full-video detections."""

from __future__ import annotations

import hashlib
import math
from itertools import pairwise
from pathlib import Path
from typing import ClassVar, Literal

import numpy as np
import typer
from numpy.typing import NDArray
from pycocotools import mask as mask_util
from pydantic import BaseModel, ConfigDict

Event = Literal["SOLID_LINE_LANE_CHANGE", "CENTER_LINE_CROSSING", "SIGNAL"]
Box = tuple[float, float, float, float]


class Detection(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    name: str
    score: float
    bbox_xyxy: Box
    mask_rle: str | None = None
    mask_size: tuple[int, int] | None = None


class Frame(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    time_sec: float
    detections: tuple[Detection, ...]


class ClipInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    duration_sec: float
    sha256: str


class TrackPoint(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    track_id: int
    time_sec: float
    detection: Detection


class Candidate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    file: str
    event: Event
    start_sec: float
    end_sec: float
    peak_sec: float
    score: float
    track_id: int | None
    bbox_xyxy: Box | None
    image_wh: tuple[int, int] | None
    reason: str


class CandidateSet(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    clips: tuple[ClipInput, ...]
    candidates: tuple[Candidate, ...]
    rules: str
    cache_manifest_sha256: str
    generator_sha256: str
    prediction_sha256: dict[str, str]


class ClipManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    videos: tuple[ClipInput, ...]


def box_iou(a: Box, b: Box) -> float:
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0


def link_cars(frames: tuple[Frame, ...]) -> tuple[tuple[TrackPoint, ...], ...]:
    """Greedy one-to-one IoU matching; lists accumulate points until frozen."""
    tracks: list[list[TrackPoint]] = []
    for frame in frames:
        cars = [d for d in frame.detections if d.name == "car" and d.score >= 0.4]
        pairs = sorted(
            (
                (box_iou(t[-1].detection.bbox_xyxy, d.bbox_xyxy), ti, di)
                for ti, t in enumerate(tracks)
                if frame.time_sec - t[-1].time_sec <= 2.1
                for di, d in enumerate(cars)
            ),
            reverse=True,
        )
        used_tracks: set[int] = set()
        used_cars: set[int] = set()
        for score, ti, di in pairs:
            if score < 0.2 or ti in used_tracks or di in used_cars:
                continue
            tracks[ti].append(
                TrackPoint(track_id=ti, time_sec=frame.time_sec, detection=cars[di])
            )
            used_tracks.add(ti)
            used_cars.add(di)
        for di, car in enumerate(cars):
            if di not in used_cars:
                ti = len(tracks)
                tracks.append(
                    [TrackPoint(track_id=ti, time_sec=frame.time_sec, detection=car)]
                )
    return tuple(tuple(t) for t in tracks)


def near_marking(detection: Detection, box: Box) -> bool:
    """Test actual mask pixels around a vehicle's approximate ground contact."""
    if detection.mask_rle is None or detection.mask_size is None:
        return False
    mask = mask_util.decode(
        {
            "size": list(detection.mask_size),
            "counts": detection.mask_rle.encode("ascii"),
        }
    )
    h, w = detection.mask_size
    x = (box[0] + box[2]) / 2
    radius_x = max(12, (box[2] - box[0]) / 2)
    radius_y = max(6, h / 60)
    return bool(
        np.any(
            mask[
                max(0, int(box[3] - radius_y)) : min(h, int(box[3] + radius_y) + 1),
                max(0, int(x - radius_x)) : min(w, int(x + radius_x) + 1),
            ]
        )
    )


def propose(
    clip: ClipInput, models: dict[str, tuple[Frame, ...]], image_wh: tuple[int, int]
) -> tuple[Candidate, ...]:
    """All three event types are considered without access to truth or hints."""
    by_time = {
        key: {f.time_sec: f.detections for f in frames}
        for key, frames in models.items()
    }
    anchors: list[Candidate] = []
    for track in link_cars(models["yolo_signal"]):
        for previous, point in pairwise(track):
            a, b = previous.detection.bbox_xyxy, point.detection.bbox_xyxy
            width = max(1.0, b[2] - b[0])
            dx = abs((b[0] + b[2] - a[0] - a[2]) / 2) / width
            dy = abs(b[3] - a[3]) / width
            t = point.time_sec
            events: tuple[tuple[Event, str, float], ...] = (
                ("SOLID_LINE_LANE_CHANGE", "mask_lane", dx),
                ("CENTER_LINE_CROSSING", "mask_center", dx),
                ("SIGNAL", "mask_stop", math.hypot(dx, dy)),
            )
            reds = [
                d.score for d in by_time["yolo_signal"][t] if d.name == "red_signal"
            ]
            for event, key, motion in events:
                if motion < 0.15 or (event == "SIGNAL" and not reds):
                    continue
                lines = [
                    d for d in by_time[key][t] if d.score >= 0.25 and near_marking(d, b)
                ]
                if not lines:
                    continue
                marking_score = max(d.score for d in lines)
                score = (
                    0.5 * marking_score
                    + 0.25 * point.detection.score
                    + 0.25 * min(motion, 1)
                )
                anchors.append(
                    Candidate(
                        file=clip.file,
                        event=event,
                        start_sec=0,
                        end_sec=0,
                        peak_sec=t,
                        score=score,
                        track_id=point.track_id,
                        bbox_xyxy=b,
                        image_wh=image_wh,
                        reason=f"moving track near {key}; motion/car_width={motion:.3f}; red_present={bool(reds)}",
                    )
                )
    return select_windows(clip, tuple(anchors))


def select_windows(
    clip: ClipInput, anchors: tuple[Candidate, ...]
) -> tuple[Candidate, ...]:
    selected: list[Candidate] = []
    for event in ("SOLID_LINE_LANE_CHANGE", "CENTER_LINE_CROSSING", "SIGNAL"):
        chosen: list[Candidate] = []
        for a in sorted(
            (p for p in anchors if p.event == event),
            key=lambda p: (-p.score, p.peak_sec),
        ):
            start = math.floor(a.peak_sec / 4) * 4
            end = min(clip.duration_sec, start + 8)
            if any(start < c.end_sec and c.start_sec < end for c in chosen):
                continue
            chosen.append(
                a.model_copy(update={"start_sec": float(start), "end_sec": end})
            )
            if len(chosen) == 2:
                break
        selected.extend(chosen)
    return tuple(selected)


def run(cache_dir: Path, output: Path) -> None:
    import cv2

    clips = ClipManifest.model_validate_json(
        (cache_dir / "manifest.json").read_text(encoding="utf-8")
    ).videos
    candidates: list[Candidate] = []
    hashes: dict[str, str] = {}
    for clip in clips:
        stem = Path(clip.file).stem
        models: dict[str, tuple[Frame, ...]] = {}
        for key in ("yolo_signal", "mask_lane", "mask_center", "mask_stop"):
            path = cache_dir / "predictions" / key / f"{stem}.jsonl"
            hashes[f"{key}/{stem}"] = hashlib.sha256(path.read_bytes()).hexdigest()
            models[key] = tuple(
                Frame.model_validate_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            )
        expected_times = [f.time_sec for f in models["yolo_signal"]]
        assert all(
            [f.time_sec for f in frames] == expected_times for frames in models.values()
        )
        image: NDArray[np.uint8] = np.asarray(
            cv2.imread(str(cache_dir / "frames" / stem / "00000.jpg")), dtype=np.uint8
        )
        h, w = map(int, image.shape[:2])
        found = propose(clip, models, (w, h))
        candidates.extend(found)
        print(
            clip.file,
            len(found),
            [(c.event, c.start_sec, c.end_sec) for c in found],
            flush=True,
        )
    result = CandidateSet(
        clips=clips,
        candidates=tuple(candidates),
        rules="car>=.4, masks/red>=.25; IoU>=.2 gap<=2.1s; motion>=.15 car widths; ground-contact mask rectangle; 8s windows step4s; top2 nonoverlapping/event; all3 types; no truth; no LRCN",
        cache_manifest_sha256=hashlib.sha256(
            (cache_dir / "manifest.json").read_bytes()
        ).hexdigest(),
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        prediction_sha256=hashes,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(result.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    typer.run(run)
