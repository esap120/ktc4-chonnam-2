import pytest

# scripts/aihub_* 는 uv 단독 실행 스크립트라 typer 가 프로젝트 의존성에 없다(CI 미설치).
pytest.importorskip("typer")

from pathlib import Path  # noqa: E402

from scripts.aihub_model_video_data import read_truth, sha256  # noqa: E402


def test_multiple_events_do_not_turn_onset_markers_into_intervals(
    tmp_path: Path,
) -> None:
    source = tmp_path / "truth.md"
    source.write_text(
        "| `a.mp4` | 60 | `SOLID_LINE_LANE_CHANGE` ×2 | **있음** | 실선 | "
        "**10–12 (11)**, **20–22 (21)** | user | 중 |\n",
        encoding="utf-8",
    )
    rows = read_truth(source)
    assert rows == [
        ("a.mp4", "SOLID_LINE_LANE_CHANGE", ((10.0, 12.0), (20.0, 22.0)), "user", "중")
    ]


def test_legal_lane_change_interval_is_not_a_positive_event(tmp_path: Path) -> None:
    source = tmp_path / "truth.md"
    source.write_text(
        "| `normal.avi` | 20 | 차로변경(점선) | 없음(합법) | 점선 | ≈10–14 | user | 중 |\n",
        encoding="utf-8",
    )
    rows = read_truth(source)
    assert rows == [("normal.avi", "NONE", (), "user", "중")]


def test_subsecond_event_boundary_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "truth.md"
    source.write_text(
        "| `boundary.mp4` | 60 | `SIGNAL` | 있음 | — | **0.5–3 (1)** | set1_g3 | 중 |\n",
        encoding="utf-8",
    )
    assert read_truth(source)[0][2] == ((0.5, 3.0),)


def test_sha256_works_on_python_310(tmp_path: Path) -> None:
    source = tmp_path / "fixture.bin"
    source.write_bytes(b"abc")
    assert (
        sha256(source)
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
