#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.11"
# dependencies = ["tensorflow==2.15.1", "numpy<2", "pydantic>=2,<3", "typer", "opencv-python==4.10.0.84"]
# ///
# How to run: python -m scripts.aihub_model_video_lrcn WEIGHTS_DIR CACHE_DIR (Python 3.10 environment from report).
"""Evaluate original 25-frame 64px BGR LRCN without inventing a normal class."""

from __future__ import annotations

import importlib
import json
import shutil
import time
from pathlib import Path
from typing import Final, Literal

import numpy as np
import typer
from pydantic import BaseModel, ConfigDict

from scripts.aihub_model_video_data import VideoTruth, sha256

CLASSES: Final = ("SIGNAL", "CENTER_LINE_CROSSING", "SOLID_LINE_LANE_CHANGE")


class Classification(BaseModel):
    model_config = ConfigDict(frozen=True)
    file: str
    mode: Literal["whole_clip", "oracle_event", "sliding_5sec"]
    event_index: int | None = None
    interval: tuple[float, float]
    input_times: tuple[float, ...]
    expected: str
    predicted: str
    probabilities: tuple[float, float, float]
    processing_ms: float


def run(weights_dir: Path, cache_dir: Path) -> None:
    """Keep blind whole-clip and sliding results separate from oracle-assisted crops."""
    load_model = importlib.import_module("tensorflow.keras.models").load_model

    weight = next(weights_dir.rglob("*.h5"))
    ascii_path = cache_dir / "lrcn.h5"
    shutil.copyfile(weight, ascii_path)
    model = load_model(str(ascii_path), compile=False)
    model(np.zeros((1, 25, 64, 64, 3), dtype=np.float32), training=False)
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    videos = [VideoTruth.model_validate(v) for v in manifest["videos"]]
    destination = cache_dir / "predictions" / "lrcn"
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {
        "weights_sha256": sha256(weight),
        "class_order": CLASSES,
        "input_shape": list(model.input_shape),
        "output_shape": list(model.output_shape),
        "preprocessing": "OpenCV BGR / resize 64x64 / divide 255 (original notebook)",
        "sequence_fps": 5,
        "device": "CPU / TensorFlow 2.15.1 native Windows",
        "normal_class": False,
        "sampling_caveat": "Original training sequence frame interval unspecified; video sampling is an adaptation.",
    }
    (destination / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    with (destination / "classifications.jsonl").open("w", encoding="utf-8") as stream:
        for video in videos:
            images = np.load(
                cache_dir / "frames" / Path(video.file).stem / "bgr64_5fps.npy"
            )
            times = np.asarray(video.sequence_times)
            windows: list[
                tuple[
                    Literal["whole_clip", "oracle_event", "sliding_5sec"],
                    int | None,
                    float,
                    float,
                ]
            ] = [("whole_clip", None, 0.0, video.duration_sec)]
            for j, (a, b) in enumerate(video.intervals):
                center = (a + b) / 2
                width = max(5.0, b - a + 2.0)
                windows.append(
                    (
                        "oracle_event",
                        j,
                        max(0, center - width / 2),
                        min(video.duration_sec, center + width / 2),
                    )
                )
            starts = list(np.arange(0, max(0.001, video.duration_sec - 5.0), 2.5))
            starts.append(max(0.0, video.duration_sec - 5.0))
            for a in sorted({float(s) for s in starts}):
                windows.append(
                    ("sliding_5sec", None, a, min(a + 5, video.duration_sec))
                )
            for mode, event_index, a, b in windows:
                candidates = np.flatnonzero((times >= a) & (times < b))
                indices = candidates[
                    np.rint(np.linspace(0, len(candidates) - 1, 25)).astype(int)
                ]
                batch = images[indices].astype(np.float32)[None] / 255.0
                start = time.perf_counter()
                probabilities = model(batch, training=False).numpy()[0]
                elapsed = (time.perf_counter() - start) * 1000
                predicted = CLASSES[int(np.argmax(probabilities))]
                row = Classification(
                    file=video.file,
                    mode=mode,
                    event_index=event_index,
                    interval=(a, b),
                    input_times=times[indices].tolist(),
                    expected=video.event,
                    predicted=predicted,
                    probabilities=probabilities.tolist(),
                    processing_ms=elapsed,
                )
                stream.write(row.model_dump_json() + "\n")
            print(f"LRCN {video.file}: {len(windows)} windows", flush=True)


if __name__ == "__main__":
    typer.run(run)
