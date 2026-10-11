"""관련 asset 선택 — 선택 후보의 IncidentClip이 lineage에 있는 asset만 넘긴다(`decisions/real-e2e-scenarios.md` §4-2)."""
from __future__ import annotations

from daesingo.case.real_e2e import select_case_assets


def _facts(ref: str, role: str | None, *lineage: tuple[str, str]) -> dict:
    return {
        "asset_ref": {"kind": "derived_asset", "ref": ref},
        "derived_role": role,
        "lineage": [{"kind": k, "ref": r} for k, r in lineage],
    }


def test_keeps_assets_derived_from_selected_clip():
    video = _facts("da_a_video", "REPORT_VIDEO", ("incident_clip", "clip_a"), ("source_asset", "sa_1"))
    image = _facts("da_a_image", "PLATE_IMAGE", ("incident_clip", "clip_a"))
    assert select_case_assets("clip_a", [video, image]) == [video, image]


def test_drops_assets_of_other_clip():
    """다른 후보 clip의 REPORT_VIDEO가 섞이면 같은 역할이 둘이 돼 evidence가 오류를 낸다 — 여기서 거른다."""
    mine = _facts("da_a_video", "REPORT_VIDEO", ("incident_clip", "clip_a"))
    other = _facts("da_b_video", "REPORT_VIDEO", ("incident_clip", "clip_b"))
    assert select_case_assets("clip_a", [other, mine]) == [mine]


def test_does_not_filter_by_role():
    """어떤 역할이 패키지에 쓰이는지는 evidence 규칙이다."""
    odd = _facts("da_a_other", "SOMETHING_ELSE", ("incident_clip", "clip_a"))
    assert select_case_assets("clip_a", [odd]) == [odd]


def test_drops_assets_without_lineage_and_matches_kind():
    no_lineage = {"asset_ref": {"kind": "source_asset", "ref": "sa_1"}, "lineage": []}
    same_ref_other_kind = _facts("da_x", "REPORT_VIDEO", ("source_asset", "clip_a"))
    assert select_case_assets("clip_a", [no_lineage, same_ref_other_kind]) == []


def test_keeps_the_clip_itself():
    """clip 자신의 AssetFacts는 lineage에 자기가 없다 — 그래도 이 후보의 asset이다."""
    clip = {"asset_ref": {"kind": "incident_clip", "ref": "clip_a"}, "lineage": [{"kind": "source_asset", "ref": "sa_1"}]}
    other_clip = {"asset_ref": {"kind": "incident_clip", "ref": "clip_b"}, "lineage": []}
    assert select_case_assets("clip_a", [clip, other_clip]) == [clip]


def test_empty_list():
    assert select_case_assets("clip_a", []) == []


def test_accepts_recording_asset_facts_models():
    """fixture 경로는 recording `AssetFacts` 모델을 그대로 넘긴다 — happy fixture의 clip_h001과 그 파생만 남는다."""
    from daesingo.case import real_e2e

    fixture = real_e2e.load_recording_fixture(real_e2e.DEFAULT_SCENARIO_ID)

    refs = [f.asset_ref.ref for f in select_case_assets("clip_h001", fixture.asset_facts)]

    assert refs == ["clip_h001", "da_h001_report_video", "da_h001_plate_image"]
    assert select_case_assets("clip_other", fixture.asset_facts) == []
