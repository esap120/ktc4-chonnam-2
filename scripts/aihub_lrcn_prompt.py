#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pydantic>=2,<3", "numpy<2", "pycocotools", "typer"]
# ///
# How to run: imported by python -m scripts.aihub_hybrid_fine.
"""Independent multi-type Fine verification with an unconfirmed LRCN hint."""

from daesingo.search.prompts import FINE_PROMPT
from scripts.aihub_hybrid_candidates import Candidate


def classification_prompt(candidate: Candidate, start: float, end: float) -> str:
    text = FINE_PROMPT.render(
        event_type="SIGNAL, CENTER_LINE_CROSSING, SOLID_LINE_LANE_CHANGE 중 실제 관찰한 종류",
        target_hint=(
            f"LRCN 분류 모델이 {candidate.start_sec:.2f}–{candidate.end_sec:.2f}초에서 "
            f"{candidate.event}를 점수 {candidate.score:.6f}로 예측했다. "
            "이는 검증되지 않은 참고 정보이며 보정된 위반 확률이 아니다. "
            "모델에는 정상 클래스가 없어 정상 영상도 위반으로 분류한다. "
            "차량 위치 힌트는 없으며 실제 대상 차량은 원본에서 독립적으로 찾아라."
        ),
        start_sec=start,
        end_sec=end,
    )
    text = text.replace(
        "OBSERVED일 때만 visual_event_type에 검증 대상\n사건을 넣고",
        "OBSERVED일 때만 visual_event_type에 직접 확인한 한 종류를 넣고",
    )
    return text + (
        "\n분류 힌트와 다른 종류의 위반도 확인하라. 위반 없음은 NOT_OBSERVED, "
        "증거 부족은 UNCERTAIN으로 답하라. 힌트에 맞추어 관찰을 추정하지 마라. "
        "차량 힌트가 없으므로 match_with_hint는 null이다. "
        "SIGNAL은 대상 차량에 해당하는 적색 신호와 그 상태에서의 정지선 통과가 "
        "모두 보일 때만 OBSERVED이다. 녹색 주행은 신호위반이 아니다. "
        "실선 변경은 실제 횡단과 해당 백색 실선을, 중앙선은 황색 중앙선 횡단을 확인하라. "
        "관찰한 횡단 순간을 temporal_facts의 at_offset_ms에 기록하라. "
        "여러 사건이 보이면 후보 본문 구간과 가장 가까운 명확한 사건 하나를 반환하라."
    )
