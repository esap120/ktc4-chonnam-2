#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy<2", "pydantic>=2,<3", "opencv-python==4.10.0.84", "typer", "torch==2.5.1"]
# ///
# How to run: python -m scripts.aihub_model_video_score CACHE_DIR OUTPUT_JSON (environment from report).
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import typer

from scripts.aihub_model_video_data import VideoTruth
from scripts.aihub_model_video_infer import MODELS, FramePrediction
from scripts.aihub_model_video_lrcn import CLASSES, Classification


def score(cache_dir: Path, output_json: Path) -> None:
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    videos = [VideoTruth.model_validate(v) for v in manifest["videos"]]
    spatial = []
    primitive_classes = {
        "mask_lane": ("SOLID_LINE_LANE_CHANGE", {"white_solid"}),
        "mask_center": (
            "CENTER_LINE_CROSSING",
            {"yellow_solid", "yellow_double_solid"},
        ),
        "mask_stop": ("SIGNAL", {"stop_line"}),
        "mask_area": ("SIGNAL", {"crosswalk", "intersection"}),
        "yolo_signal": ("SIGNAL", {"red_signal"}),
    }
    for key, _, _ in MODELS:
        root = cache_dir / "predictions" / key
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        latencies, per_video, primitive_events = [], [], []
        counts = {str(t): Counter() for t in (0.25, 0.5, 0.8)}
        for video in videos:
            lines = (
                (root / f"{Path(video.file).stem}.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            rows = [FramePrediction.model_validate_json(line) for line in lines]
            if tuple(r.time_sec for r in rows) != video.frame_times:
                raise RuntimeError(
                    f"Incomplete or mismatched frame run: {key}/{video.file}"
                )
            latencies.extend(r.processing_ms for r in rows)
            at_thresholds = []
            for threshold in (0.25, 0.5, 0.8):
                classes = Counter(
                    d.name for r in rows for d in r.detections if d.score >= threshold
                )
                frames_with = sum(
                    any(d.score >= threshold for d in r.detections) for r in rows
                )
                counts[str(threshold)].update(classes)
                at_thresholds.append(
                    {
                        "threshold": threshold,
                        "frames_with_detection": frames_with,
                        "class_counts": dict(classes),
                    }
                )
            per_video.append(
                {
                    "file": video.file,
                    "expected": video.event,
                    "frames": len(rows),
                    "thresholds": at_thresholds,
                }
            )
            if key in primitive_classes:
                expected, wanted = primitive_classes[key]
                if video.event == expected:
                    for event_index, (a, b) in enumerate(video.intervals):
                        event_rows = [r for r in rows if a <= r.time_sec <= b]
                        at_thresholds = []
                        for threshold in (0.25, 0.5, 0.8):
                            hits = sum(
                                any(
                                    d.name in wanted and d.score >= threshold
                                    for d in r.detections
                                )
                                for r in event_rows
                            )
                            at_thresholds.append(
                                {
                                    "threshold": threshold,
                                    "frames_with_primitive": hits,
                                    "frames_sampled": len(event_rows),
                                    "any_primitive": hits > 0,
                                }
                            )
                        primitive_events.append(
                            {
                                "file": video.file,
                                "event_index": event_index,
                                "interval": [a, b],
                                "thresholds": at_thresholds,
                            }
                        )
        spatial.append(
            {
                "key": key,
                "metadata": metadata,
                "frames": len(latencies),
                "latency_mean_ms": float(np.mean(latencies)),
                "latency_p50_ms": float(np.median(latencies)),
                "latency_p95_ms": float(np.percentile(latencies, 95)),
                "warm_inference_fps": 1000 / float(np.mean(latencies)),
                "class_counts": {k: dict(v) for k, v in counts.items()},
                "per_video": per_video,
                "primitive_events": primitive_events,
                "spatial_accuracy": None,
                "limitation": "No box/mask GT. Primitive presence is not violation or localization recall.",
            }
        )
    root = cache_dir / "predictions" / "lrcn"
    classifications = [
        Classification.model_validate_json(line)
        for line in (root / "classifications.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    classification_metrics = []
    for mode in ("whole_clip", "oracle_event"):
        rows = [r for r in classifications if r.mode == mode and r.expected != "NONE"]
        matrix: dict[str, dict[str, int]] = {
            c: dict.fromkeys(CLASSES, 0) for c in CLASSES
        }
        for row in rows:
            matrix[row.expected][row.predicted] += 1
        correct = sum(r.expected == r.predicted for r in rows)
        classification_metrics.append(
            {
                "mode": mode,
                "correct": correct,
                "total": len(rows),
                "accuracy": correct / len(rows),
                "confusion_matrix": matrix,
            }
        )
    negatives = [
        r for r in classifications if r.mode == "whole_clip" and r.expected == "NONE"
    ]
    sliding = [r for r in classifications if r.mode == "sliding_5sec"]
    sliding_events = []
    for video in videos:
        for event_index, (a, b) in enumerate(video.intervals):
            rows = [
                r
                for r in sliding
                if r.file == video.file and r.interval[0] < b and r.interval[1] > a
            ]
            hits = [
                r
                for r in rows
                if r.predicted == video.event and max(r.probabilities) >= 0.8
            ]
            sliding_events.append(
                {
                    "file": video.file,
                    "event_index": event_index,
                    "class_correct_overlap_at_0_8": bool(hits),
                }
            )
    negative_sliding = [
        {
            "file": v.file,
            "total_windows": sum(r.file == v.file for r in sliding),
            "high_confidence_windows": sum(
                r.file == v.file and max(r.probabilities) >= 0.8 for r in sliding
            ),
        }
        for v in videos
        if v.event == "NONE"
    ]
    dataset = {
        "video_count": len(videos),
        "duration_sec": sum(v.duration_sec for v in videos),
        "frames_per_spatial_model": sum(len(v.frame_times) for v in videos),
        "positive_videos": sum(v.event != "NONE" for v in videos),
        "negative_videos": sum(v.event == "NONE" for v in videos),
        "positive_events": sum(len(v.intervals) for v in videos),
        "truth_sha256": manifest["truth_sha256"],
        "videos": [
            {
                "file": v.file,
                "event": v.event,
                "intervals": v.intervals,
                "sha256": v.sha256,
                "source": v.source,
                "confidence": v.confidence,
            }
            for v in videos
        ],
    }
    result = {
        "dataset": dataset,
        "spatial": spatial,
        "lrcn": {
            "metadata": json.loads(
                (root / "metadata.json").read_text(encoding="utf-8")
            ),
            "metrics": classification_metrics,
            "forced_violation_negative_clips": len(negatives),
            "negative_clips": len(negatives),
            "latency_mean_ms": float(
                np.mean([r.processing_ms for r in classifications])
            ),
            "latency_p95_ms": float(
                np.percentile([r.processing_ms for r in classifications], 95)
            ),
            "sliding_class_overlap_diagnostic": sliding_events,
            "sliding_negative_diagnostic": negative_sliding,
            "whole_clip_predictions": [
                r.model_dump() for r in classifications if r.mode == "whole_clip"
            ],
            "oracle_event_predictions": [
                r.model_dump() for r in classifications if r.mode == "oracle_event"
            ],
            "warning": "No normal/helmet class. Oracle event accuracy is not end-to-end recall; sliding overlap is not target/localization accuracy.",
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "dataset": {k: v for k, v in dataset.items() if k != "videos"},
                "lrcn": classification_metrics,
                "spatial": [
                    {
                        k: m[k]
                        for k in (
                            "key",
                            "frames",
                            "latency_mean_ms",
                            "warm_inference_fps",
                        )
                    }
                    for m in spatial
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    typer.run(score)
