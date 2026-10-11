#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.11"
# dependencies = ["torch==2.5.1", "torchvision==0.20.1", "numpy<2", "opencv-python==4.10.0.84", "pillow==9.5.0", "pydantic>=2,<3", "typer", "fvcore", "iopath", "pycocotools", "omegaconf", "hydra-core", "termcolor", "cloudpickle", "tabulate", "tensorboard", "pandas", "seaborn", "requests", "ipython", "psutil", "scipy", "gitpython", "setuptools<81"]
# ///
# How to run: python -m scripts.aihub_model_video_infer WEIGHTS_DIR CACHE_DIR SOURCES_DIR (CUDA environment from report).
"""Run all eight spatial AI Hub models over the same cached timestamped frames."""

from __future__ import annotations

import gc
import json
import os
import time
from pathlib import Path
from typing import Final

import cv2
import numpy as np
import torch
import typer
from pydantic import BaseModel, ConfigDict

from scripts.aihub_model_video_adapters import (
    Detection,
    Detector,
    MaskDetector,
    YoloDetector,
    overlay,
)
from scripts.aihub_model_video_data import VideoTruth, sha256

MODELS: Final = (
    ("yolo_signal", "model_객체탐지_신호위반.pt", ()),
    ("yolo_center", "model_객체탐지_중앙선침범.pt", ()),
    ("yolo_lane", "model_객체탐지_진로변경.pt", ()),
    ("yolo_helmet", "model_객체탐지_안전모.pt", ()),
    ("mask_stop", "model_차선탐지_신호위반.pth", ("stop_line",)),
    (
        "mask_center",
        "model_차선탐지_중앙선침범.pth",
        ("yellow_solid", "yellow_double_solid"),
    ),
    ("mask_lane", "model_차선탐지_진로변경.pth", ("white_solid",)),
    ("mask_area", "model_교통영역탐지.pth", ("crosswalk", "intersection")),
)


class FramePrediction(BaseModel):
    model_config = ConfigDict(frozen=True)
    file: str
    time_sec: float
    processing_ms: float
    detections: tuple[Detection, ...]


def run(
    weights_dir: Path,
    cache_dir: Path,
    sources_dir: Path,
    model_filter: str = "",
    confidence: float = 0.25,
) -> None:
    """Preserve raw predictions, measured adapter latency, weight hashes and overlays."""
    os.environ["YOLOv5_AUTOINSTALL"] = "false"
    torch.set_num_threads(4)
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    videos = [VideoTruth.model_validate(v) for v in manifest["videos"]]
    for key, filename, names in MODELS:
        if model_filter and key not in model_filter.split(","):
            continue
        weight = next(weights_dir.rglob(filename))
        detector: Detector
        if names:
            detector = MaskDetector(
                weight, sources_dir / "detectron2", names, confidence
            )
        else:
            detector = YoloDetector(weight, sources_dir / "yolov5", confidence)
        image = cv2.imread(
            str(cache_dir / "frames" / Path(videos[0].file).stem / "00000.jpg")
        )
        for _ in range(3):
            detector.predict(np.asarray(image, dtype=np.uint8))
        torch.cuda.synchronize()
        destination = cache_dir / "predictions" / key
        destination.mkdir(parents=True, exist_ok=True)
        metadata = {
            "key": key,
            "weights_sha256": sha256(weight),
            "weights_file": filename,
            "confidence": confidence,
            "names": detector.names,
            "torch": torch.__version__,
            "device": torch.cuda.get_device_name(0),
            "source_revision": "d1e04565d3bec8719335b88be9e9b961bf3ec464"
            if names
            else "915bbf294bb74c859f0b41f1c23bc395014ea679",
            "warmup_frames": 3,
            "jpeg_quality": 95,
            "sampling_fps": 1,
            "mask_config": "mask_rcnn_R_50_FPN_3x / short edge 800 / max 1333"
            if names
            else None,
        }
        (destination / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        for video in videos:
            stem = Path(video.file).stem
            center = (
                sum(video.intervals[0]) / 2
                if video.intervals
                else min(10.0, video.duration_sec / 2)
            )
            inspect_index = min(
                range(len(video.frame_times)),
                key=lambda i: abs(video.frame_times[i] - center),
            )
            with (destination / f"{stem}.jsonl").open("w", encoding="utf-8") as stream:
                for i, seconds in enumerate(video.frame_times):
                    image = cv2.imread(
                        str(cache_dir / "frames" / stem / f"{i:05d}.jpg")
                    )
                    torch.cuda.synchronize()
                    start = time.perf_counter()
                    image = np.asarray(image, dtype=np.uint8)
                    detections = detector.predict(image)
                    torch.cuda.synchronize()
                    row = FramePrediction(
                        file=video.file,
                        time_sec=seconds,
                        processing_ms=(time.perf_counter() - start) * 1000,
                        detections=detections,
                    )
                    stream.write(row.model_dump_json() + "\n")
                    if i == inspect_index:
                        rendered = overlay(image, detections)
                        cv2.putText(
                            rendered,
                            f"{key} t={seconds:.2f}s",
                            (20, 35),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.9,
                            (255, 255, 255),
                            2,
                        )
                        cv2.imwrite(str(destination / f"{stem}.jpg"), rendered)
            print(f"{key}: {stem}: {len(video.frame_times)} frames", flush=True)
        del detector
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    typer.run(run)
