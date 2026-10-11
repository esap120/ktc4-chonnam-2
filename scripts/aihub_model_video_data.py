#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy<2", "opencv-python==4.10.0.84", "typer", "pydantic>=2,<3"]
# ///
# How to run: install uv, then uv run scripts/aihub_model_video_data.py VIDEO_DIR OUTPUT_DIR
"""Cache timestamped video frames and parse the existing human event truth."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Final

import cv2
import numpy as np
import typer
from pydantic import BaseModel, ConfigDict

EVENTS: Final = ("SIGNAL", "CENTER_LINE_CROSSING", "SOLID_LINE_LANE_CHANGE")


class VideoTruth(BaseModel):
    model_config = ConfigDict(frozen=True)
    file: str
    event: str
    intervals: tuple[tuple[float, float], ...]
    source: str
    confidence: str
    duration_sec: float
    fps: float
    source_frames: int
    sha256: str
    frame_times: tuple[float, ...]
    sequence_times: tuple[float, ...]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def read_truth(
    path: Path,
) -> list[tuple[str, str, tuple[tuple[float, float], ...], str, str]]:
    """Read positive event intervals; negatives retain an empty interval list."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cols = [
            c.strip().replace("`", "").replace("**", "")
            for c in line.strip("|").split("|")
        ]
        event = next((e for e in EVENTS if e in cols[2]), "NONE")
        intervals = (
            tuple(
                (float(a), float(b))
                for a, b in re.findall(
                    r"(\d+(?:\.\d+)?)\s*[–−-]\s*(\d+(?:\.\d+)?)", cols[5]
                )
            )
            if event != "NONE"
            else ()
        )
        rows.append((cols[0], event, intervals, cols[6], cols[7]))
    return rows


def prepare(video_dir: Path, output_dir: Path) -> None:
    """Decode each video once, cache native-size 1fps JPEGs and 5fps 64px BGR."""
    output_dir.mkdir(parents=True, exist_ok=True)
    truths = []
    for filename, event, intervals, source, confidence in read_truth(
        video_dir / "정답지.md"
    ):
        src = video_dir / filename
        cache = output_dir / "frames" / src.stem
        cache.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            raise OSError(f"Video cannot be opened: {src}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_times, sequence_times, small_frames = [], [], []
        idx, next_full, next_small = 0, 0.0, 0.0
        try:
            while True:
                ok, image = cap.read()
                if not ok:
                    break
                time_sec = idx / fps
                if time_sec + 0.5 / fps >= next_full:
                    dest = cache / f"{len(frame_times):05d}.jpg"
                    if not cv2.imwrite(
                        str(dest), image, [cv2.IMWRITE_JPEG_QUALITY, 95]
                    ):
                        raise OSError(f"Image could not be written: {dest}")
                    frame_times.append(time_sec)
                    next_full += 1.0
                if time_sec + 0.5 / fps >= next_small:
                    small_frames.append(cv2.resize(image, (64, 64)))
                    sequence_times.append(time_sec)
                    next_small += 0.2
                idx += 1
        finally:
            cap.release()
        np.save(cache / "bgr64_5fps.npy", np.stack(small_frames))
        truth = VideoTruth(
            file=filename,
            event=event,
            intervals=intervals,
            source=source,
            confidence=confidence,
            duration_sec=count / fps,
            fps=fps,
            source_frames=count,
            sha256=sha256(src),
            frame_times=tuple(frame_times),
            sequence_times=tuple(sequence_times),
        )
        truths.append(truth)
        print(
            f"{src.stem}: {len(frame_times)} full frames, {len(small_frames)} sequence frames",
            flush=True,
        )
    payload = {
        "truth_sha256": sha256(video_dir / "정답지.md"),
        "videos": [t.model_dump() for t in truths],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    typer.run(prepare)
