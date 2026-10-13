"""`case.report_video_not_generated` — #351 [R-2] case 결정.

발동 조건: evidence가 있고(`record_id` non-null — 응답 전 부분 투영이 아니다), 선택된 후보의 신고 상황 응답이
끝났고(`CONFIRMED` · `CORRECTED` · `USER_UNSURE`), FINAL 요건의 `package.asset.report_video.exists`가 `PASS`가
아닐 때. 실행 중에도 붙인다 — web은 이 notice가 없으면 응답 대기가 아닐 때 영상 칸을 있는 것처럼 그린다.
「신고용 영상 만들기」(`GENERATE_REPORT_VIDEO`)는 이전 `REPORT_VIDEO_EXPORT` JobRecord가 있고 그 kind가
`running_jobs`에 없을 때만 싣는다 — 버튼은 실패 뒤 재시도다(#351 [R-3]).
"""
import copy
import json
from pathlib import Path

import pytest

from daesingo.case import service

MOCK_ROOT = Path(__file__).resolve().parents[2] / "data" / "mock"
CODE = "case.report_video_not_generated"


def _responded_view_without_video(situation: str = "CONFIRMED") -> dict:
    """`happy_001` rev4(READY · CONFIRMED)에서 신고용 영상만 없는 상태 — Package가 영상 때문에 나가지 않았다."""
    with open(MOCK_ROOT / "case" / "scenario_happy_001.json", encoding="utf-8") as fh:
        rev4 = next(v for v in json.load(fh)["case_views"] if v["case_rev"] == 4)
    view = copy.deepcopy(rev4)
    view["stage"] = "EVIDENCE_REVIEW"
    view["package"] = None
    view["notices"] = []
    view["running_jobs"] = []
    for c in view["candidates"]:
        if c["selected"]:
            c["situation_confirmation"] = situation
    for check in view["requirements_package"]["checks"]:
        if check["code"] == "package.asset.report_video.exists":
            check.update(outcome="UNKNOWN", reason_code="asset.fact_missing", subject_refs=[])
    view["requirements_package"]["readiness"] = "UNKNOWN"
    return view


def _notice(view: dict) -> dict | None:
    return next((n for n in view["notices"] if n["code"] == CODE), None)


def test_notice_shape():
    assert service.REPORT_VIDEO_NOT_GENERATED_NOTICE == {
        "code": CODE,
        "severity": "INFO",
        "blocking": False,
        "message_key": "notice.report_video_not_generated",
        "actions": ["GENERATE_REPORT_VIDEO"],
    }


@pytest.mark.parametrize("situation", ["CONFIRMED", "CORRECTED", "USER_UNSURE"])
def test_notice_without_button_before_any_export_order(situation):
    # 발주한 적이 없으면 버튼이 늘 거부된다(command가 이전 JobRecord를 요구) — 싣지 않는다.
    notice = _notice(service.derive_notices(_responded_view_without_video(situation)))
    assert notice is not None
    assert notice["actions"] == []


def test_button_after_a_finished_export_order():
    notice = _notice(service.derive_notices(_responded_view_without_video(), report_video_export_basis=True))
    assert notice["actions"] == ["GENERATE_REPORT_VIDEO"]


def test_notice_stays_without_button_while_export_runs():
    # 실행 중에도 notice는 남는다 — 거두면 web이 없는 영상을 있는 것처럼 그린다. 버튼만 뺀다.
    view = _responded_view_without_video()
    view["running_jobs"] = [
        {"job_id": "job_rv_2", "kind": "REPORT_VIDEO_EXPORT", "label_key": "job.report_video_export", "status": "RUNNING"}
    ]
    notice = _notice(service.derive_notices(view, report_video_export_basis=True))
    assert notice is not None
    assert notice["actions"] == []


def test_no_notice_before_situation_response():
    # 응답 전에는 신고용 영상을 만들지 않는다(Flow 「신고자료 묶음 전」) — 이유는 `case.situation_response_pending`.
    view = service.derive_notices(_responded_view_without_video("NOT_ASKED"))
    assert _notice(view) is None


def test_no_notice_when_report_video_is_available():
    view = _responded_view_without_video()
    for check in view["requirements_package"]["checks"]:
        if check["code"] == "package.asset.report_video.exists":
            check["outcome"] = "PASS"
    assert _notice(service.derive_notices(view)) is None


def test_no_notice_before_final_requirements():
    # FINAL 요건을 아직 계산하지 않았으면 영상이 없는지 모른다 — 지어내지 않는다.
    view = _responded_view_without_video()
    view["requirements_package"] = None
    assert _notice(service.derive_notices(view)) is None


def test_no_notice_on_partial_projection():
    # 응답 전 부분 투영(`record_id=null`, #239)은 신고자료 묶음 전이다.
    view = _responded_view_without_video()
    view["evidence"]["record_id"] = None
    assert _notice(service.derive_notices(view)) is None
