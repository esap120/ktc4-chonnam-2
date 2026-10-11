import pytest

# scripts/aihub_* 는 uv 단독 실행 스크립트라 typer·pycocotools 가 프로젝트 의존성에 없다(CI 미설치).
pytest.importorskip("typer")
pytest.importorskip("pycocotools")

from scripts.aihub_hybrid_candidates import (  # noqa: E402
    Candidate,
    ClipInput,
    Detection,
    Frame,
    link_cars,
    select_windows,
)


def test_tracking_keeps_identity_when_detection_order_changes() -> None:
    # Given
    left = Detection(name="car", score=0.9, bbox_xyxy=(10, 10, 30, 30))
    right = Detection(name="car", score=0.9, bbox_xyxy=(80, 10, 100, 30))
    frames = (
        Frame(time_sec=0, detections=(left, right)),
        Frame(time_sec=1, detections=(right, left)),
    )
    # When
    tracks = link_cars(frames)
    # Then
    assert [(p[0].track_id, p[1].track_id) for p in tracks] == [(0, 0), (1, 1)]


def test_candidate_selection_is_bounded_and_needs_no_truth_fields() -> None:
    # Given
    clip = ClipInput(file="normal.mp4", duration_sec=12, sha256="x")
    triggers = (
        Candidate(
            file=clip.file,
            event="SIGNAL",
            peak_sec=1,
            score=0.9,
            start_sec=0,
            end_sec=0,
            track_id=0,
            bbox_xyxy=(0, 0, 20, 20),
            image_wh=(100, 100),
            reason="red and moving vehicle",
        ),
        Candidate(
            file=clip.file,
            event="SIGNAL",
            peak_sec=11,
            score=0.8,
            start_sec=0,
            end_sec=0,
            track_id=1,
            bbox_xyxy=(0, 0, 20, 20),
            image_wh=(100, 100),
            reason="red and moving vehicle",
        ),
    )
    # When
    candidates = select_windows(clip, triggers)
    # Then
    assert [(c.start_sec, c.end_sec) for c in candidates] == [(0, 8), (8, 12)]
    assert "event" not in ClipInput.model_fields
    assert "intervals" not in ClipInput.model_fields
