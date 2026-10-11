import pytest

# scripts/aihub_* 는 uv 단독 실행 스크립트라 typer·pycocotools 가 프로젝트 의존성에 없다(CI 미설치).
pytest.importorskip("typer")
pytest.importorskip("pycocotools")

from scripts.aihub_hybrid_candidates import ClipInput  # noqa: E402
from scripts.aihub_hybrid_score import Truth  # noqa: E402
from scripts.aihub_lrcn_candidates import Prediction, select  # noqa: E402
from scripts.aihub_lrcn_prompt import classification_prompt  # noqa: E402
from scripts.aihub_lrcn_score import score_event  # noqa: E402
from tests.search.test_aihub_hybrid_score import make_result  # noqa: E402


def test_selection_ignores_oracle_and_truth_and_limits_nonoverlapping_windows() -> None:
    clip = ClipInput(file="test.mp4", duration_sec=20, sha256="hash")
    rows = tuple(
        Prediction.model_validate(
            {
                "file": clip.file,
                "mode": mode,
                "interval": interval,
                "predicted": "SIGNAL",
                "probabilities": probabilities,
                "expected": "SECRET_TRUTH",
            }
        )
        for mode, interval, probabilities in (
            ("oracle_event", (0, 5), (1, 0, 0)),
            ("whole_clip", (0, 20), (1, 0, 0)),
            ("sliding_5sec", (2.5, 7.5), (0.99, 0.005, 0.005)),
            ("sliding_5sec", (5, 10), (0.98, 0.01, 0.01)),
            ("sliding_5sec", (10, 15), (0.97, 0.02, 0.01)),
            ("sliding_5sec", (15, 20), (0.96, 0.02, 0.02)),
        )
    )
    selected = select(clip, rows)
    assert [(c.start_sec, c.end_sec) for c in selected] == [(2.5, 7.5), (10, 15)]
    assert all(c.bbox_xyxy is None and c.track_id is None for c in selected)
    assert "expected" not in rows[0].model_dump()
    prompt = classification_prompt(selected[0], 0, 11.5)
    assert "다른 종류의 위반도 확인" in prompt
    assert "검증 대상\n사건을 넣고" not in prompt


def test_scoring_credits_fine_type_correction_but_not_wrong_time_or_failed_call() -> (
    None
):
    row = make_result()
    candidate = row.candidate.model_copy(update={"event": "SIGNAL"})
    row = row.model_copy(update={"candidate": candidate})
    truth = Truth(
        file="test.mp4", event="SOLID_LINE_LANE_CHANGE", intervals=((0, 2), (5, 7))
    )
    scores = tuple(score_event(truth, t, (candidate,), (row,)) for t in truth.intervals)
    assert scores[0].predicted_type_core == ()
    assert scores[0].corrected_type_padded == (0,)
    assert scores[1].observed_padded == ()
    failed = row.model_copy(update={"failure": "RESPONSE_TIME_OUT_OF_BOUNDS"})
    assert score_event(truth, (0, 2), (candidate,), (failed,)).observed_padded == ()
