import pytest

# scripts/aihub_* 는 uv 단독 실행 스크립트라 typer·pycocotools 가 프로젝트 의존성에 없다(CI 미설치).
pytest.importorskip("typer")
pytest.importorskip("pycocotools")

from daesingo.search.schemas import FineResponse  # noqa: E402
from scripts.aihub_hybrid_candidates import Candidate  # noqa: E402
from scripts.aihub_hybrid_fine import FineResult  # noqa: E402
from scripts.aihub_hybrid_score import Truth, accepted, score_event  # noqa: E402


def make_result(failure: str | None = None) -> FineResult:
    candidate = Candidate(
        file="test.mp4",
        event="SOLID_LINE_LANE_CHANGE",
        start_sec=0,
        end_sec=3,
        peak_sec=1,
        score=0.8,
        track_id=1,
        bbox_xyxy=(0, 0, 10, 10),
        image_wh=(100, 100),
        reason="test",
    )
    response = FineResponse.model_validate(
        {
            "verification": "OBSERVED",
            "visual_event_type": "SOLID_LINE_LANE_CHANGE",
            "target": {
                "association_status": "MATCHED",
                "described_as": "car",
                "match_with_hint": True,
                "association_confidence": 0.9,
                "track_ref": "1",
            },
            "primitives": [],
            "temporal_facts": [],
            "uncertainties": [],
        }
    )
    return FineResult(
        candidate_index=0,
        candidate=candidate,
        candidates_sha256="hash",
        window=(0, 3),
        target_hint="car",
        frames=12,
        frame_sha256=(),
        prompt_sha256="hash",
        model="gpt-5.6-sol",
        response=response,
        input_tokens=1,
        output_tokens=1,
        latency_sec=1,
        failure=failure,
    )


def test_multi_event_clip_does_not_credit_an_uncovered_second_event() -> None:
    # Given
    truth = Truth(
        file="test.mp4", event="SOLID_LINE_LANE_CHANGE", intervals=((0, 2), (5, 7))
    )
    row = make_result()
    # When
    scores = tuple(
        score_event(truth, t, (row.candidate,), (row,)) for t in truth.intervals
    )
    # Then
    assert [bool(s.observed_padded_indices) for s in scores] == [True, False]


def test_invalid_time_response_is_not_accepted_even_if_observed() -> None:
    # Given
    row = make_result("RESPONSE_TIME_OUT_OF_BOUNDS")
    # When
    result = accepted(row)
    # Then
    assert result is False
