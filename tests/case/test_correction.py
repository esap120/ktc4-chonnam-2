"""`correction.edit_time_hint()`/`reselect_candidate()` — `TIME_HINT_EDIT`/`OTHER_CANDIDATE`
`CorrectionRecord` 제출과 domain state 반영(`regress_to_searching()`/`reselect_candidate()`)을
한 번에 묶는 orchestration 레이어. `docs/modules/case/doc-research/부분 재실행 정책 표 초안
v1...md`(연구 메모, decisions/로 승격되지 않은 초안) 1·2행 그대로 구현했다 — 실제 fixture는
없으므로 이 테스트가 유일한 검증이다.
"""
import pytest

from daesingo.case import correction
from daesingo.case.domain import Candidate, CaseAggregate, InvalidTransition


def _case_at_evidence_review() -> CaseAggregate:
    case = CaseAggregate.intake(
        case_id="case_hint001",
        hints={"time": "18시쯤", "vehicle": "흰색 SUV"},
        manifest_summary={"file_count": 2},
    )
    case.start_search()
    case.receive_candidates([
        Candidate(candidate_id="c1", at="t1", at_provenance="p1", observed="obs1", thumb_ref="fr1"),
        Candidate(candidate_id="c2", at="t2", at_provenance="p2", observed="obs2", thumb_ref="fr2"),
    ])
    case.select_candidate("c1")
    return case


def test_edit_time_hint_regresses_to_searching_and_records_only_changed_fields():
    case = _case_at_evidence_review()
    rev_before = case.case_rev

    record = correction.edit_time_hint(case, {"time": "19시쯤", "vehicle": "흰색 SUV"})

    assert record is not None
    assert record["kind"] == "TIME_HINT_EDIT"
    assert record["target_field"] == "hints"
    # vehicle은 기존과 동일값이라 변경분에서 빠진다 — time만 담긴다.
    assert record["previous_value"] == {"time": "18시쯤"}
    assert record["new_value"] == {"time": "19시쯤"}

    assert case.stage == "SEARCHING"
    assert case.candidates == []
    assert case.hints["time"] == "19시쯤"
    assert case.hints["vehicle"] == "흰색 SUV"  # 안 건드린 힌트는 그대로
    assert case.case_rev == rev_before + 1  # 정확히 한 번만 오른다


def test_edit_time_hint_with_no_actual_change_creates_nothing():
    case = _case_at_evidence_review()
    rev_before = case.case_rev
    stage_before = case.stage

    record = correction.edit_time_hint(case, {"time": "18시쯤"})  # 기존과 완전히 동일

    assert record is None
    assert case.case_rev == rev_before
    assert case.stage == stage_before  # 역행도 하지 않는다
    assert case.correction_records == []


def test_edit_time_hint_rejected_while_searching_leaves_case_unchanged():
    """탐색 실패로 `SEARCHING`에 머문 case — 역행이 거부되면 기록·`hints`·`case_rev`가 남지 않는다
    (#166과 같은 원칙, orchestration 지표 4차 측정)."""
    case = CaseAggregate.intake(case_id="case_hint002", hints={"time": "18시쯤"}, manifest_summary={})
    case.start_search()
    rev_before = case.case_rev

    with pytest.raises(InvalidTransition):
        correction.edit_time_hint(case, {"time": "19시쯤"})

    assert case.case_rev == rev_before
    assert case.correction_records == []
    assert case.hints == {"time": "18시쯤"}
    assert case.stage == "SEARCHING"


@pytest.mark.parametrize("candidates", [[], ["c1"]], ids=["no_candidates", "before_selection"])
def test_value_correction_before_selection_is_rejected_without_change(candidates):
    """번호판·시각 같은 값 정정은 후보를 고른 뒤(`EVIDENCE_REVIEW`·`READY`)에만 받는다 — 상태 기계
    설계 초안 v1 §4(`CANDIDATE_REVIEW`: 「아직 선택 전」). 거부되면 기록·`case_rev`가 남지 않는다."""
    case = CaseAggregate.intake(case_id="case_corr_pre", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates([
        Candidate(candidate_id=c, at="t", at_provenance="p", observed="o", thumb_ref="f") for c in candidates
    ])
    rev_before = case.case_rev

    with pytest.raises(InvalidTransition):
        correction.apply_correction(case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
                                    previous_value=None, new_value="12가3456")

    assert case.case_rev == rev_before
    assert case.correction_records == []


def test_value_correction_while_searching_is_rejected():
    case = CaseAggregate.intake(case_id="case_corr_search", hints={}, manifest_summary={})
    case.start_search()

    with pytest.raises(InvalidTransition):
        correction.apply_correction(case, kind="EVENT_TIME_MANUAL", target_field="occurred_at",
                                    previous_value=None, new_value="2026-08-24T18:11:00+09:00")
    assert case.correction_records == []


def test_time_hint_edit_still_allowed_with_no_candidates():
    """결과 없음(후보 0개)의 출구가 단서 수정이다(이슈 #31 W-1) — case 전체 값은 선택과 무관하다."""
    case = CaseAggregate.intake(case_id="case_hint_empty", hints={"time": "18시쯤"}, manifest_summary={})
    case.start_search()
    case.receive_candidates([])

    assert correction.edit_time_hint(case, {"time": "19시쯤"}) is not None
    assert case.stage == "SEARCHING"


def _reviewed_ready_case() -> CaseAggregate:
    case = _case_at_evidence_review()
    case.mark_ready(report_package={"package_ref": {"kind": "report_package", "ref": "pkg_test_001"}})
    case.mark_reviewed()
    return case


def test_value_correction_in_ready_returns_to_evidence_review_keeping_user_reviewed():
    """READY는 PACKAGE_READY 파생 gate다 — 다시 조립되는 값 정정이 오면 gate를 다시 봐야 하므로 내린다
    (상태 기계 설계 초안 v1 §3, CaseView 계약 §10-9). `user_reviewed`는 필드 수정과 별개다(#173)."""
    case = _reviewed_ready_case()
    rev_before = case.case_rev

    correction.apply_correction(case, kind="EVENT_TIME_MANUAL", target_field="occurred_at",
                                previous_value="2026-08-24T18:05:12+09:00", new_value="2026-08-24T18:06:00+09:00")

    assert case.stage == "EVIDENCE_REVIEW"
    assert case.user_reviewed is True
    assert case.case_rev == rev_before + 1


def test_noop_correction_in_ready_changes_nothing():
    case = _reviewed_ready_case()
    rev_before = case.case_rev

    assert correction.apply_correction(case, kind="EVENT_TIME_MANUAL", target_field="occurred_at",
                                       previous_value="x", new_value="x") is None
    assert case.stage == "READY"
    assert case.case_rev == rev_before


def test_situation_response_in_ready_returns_to_evidence_review():
    case = _reviewed_ready_case()

    case.record_situation_response("USER_UNSURE", responded_at="2026-10-02T17:00:00+09:00")

    assert case.stage == "EVIDENCE_REVIEW"
    assert case.user_reviewed is True


def test_edit_time_hint_rejects_unknown_field():
    case = _case_at_evidence_review()
    import pytest
    with pytest.raises(ValueError):
        correction.edit_time_hint(case, {"nonexistent_field": "x"})


def test_edit_time_hint_supersede_chain_for_repeated_edits():
    case = _case_at_evidence_review()
    first = correction.edit_time_hint(case, {"time": "19시쯤"})
    # 두 번째 편집을 하려면 다시 EVIDENCE_REVIEW까지 가야 한다(SEARCHING으로 역행했으므로).
    case.receive_candidates([Candidate(candidate_id="c3", at=None, at_provenance=None, observed="obs3", thumb_ref="fr3")])
    case.select_candidate("c3")
    second = correction.edit_time_hint(case, {"time": "20시쯤"})

    # hints는 case 전체에 걸린 값이라 후보가 바뀌어도 chain이 이어진다.
    assert second["supersedes_ref"] == {"kind": "correction_record", "ref": first["correction_id"]}


def test_reselect_candidate_submits_other_candidate_correction_and_bumps_case_rev():
    case = _case_at_evidence_review()
    rev_before = case.case_rev

    record = correction.reselect_candidate(case, "c2")

    assert record["kind"] == "OTHER_CANDIDATE"
    assert record["target_field"] == "candidate.selected_id"
    assert record["previous_value"] == "c1"
    assert record["new_value"] == "c2"
    assert case.stage == "EVIDENCE_REVIEW"  # 제자리
    assert case.case_rev == rev_before + 1  # apply_correction()이 한 번 올린다
    assert [c.candidate_id for c in case.candidates if c.selected] == ["c2"]


# ── 재선택 원자성(#166) · READY 재선택(#173 E-4) ─────────────────────────


def _snapshot(case: CaseAggregate) -> tuple:
    return (
        case.case_rev,
        case.selection_rev,
        case.stage,
        [c.selected for c in case.candidates],
        len(case.correction_records),
    )


@pytest.mark.parametrize("bad_id", ["does-not-exist", "c1"])
def test_rejected_reselect_leaves_no_side_effects(bad_id):
    """#166: 거부된 재선택은 case_rev·CorrectionRecord·선택을 바꾸지 않는다. `c1`은 이미 선택된
    후보라 값이 바뀌지 않는 요청이다(correction-record §8-7: 무변경 입력은 기록하지 않음)."""
    case = _case_at_evidence_review()
    before = _snapshot(case)

    with pytest.raises(InvalidTransition):
        correction.reselect_candidate(case, bad_id)

    assert _snapshot(case) == before


def test_rejected_reselect_outside_allowed_stage_is_atomic():
    case = CaseAggregate.intake(case_id="case_rs001", hints={}, manifest_summary={})
    case.start_search()
    case.receive_candidates([
        Candidate(candidate_id="c1", at=None, at_provenance=None, observed="o1", thumb_ref=None),
        Candidate(candidate_id="c2", at=None, at_provenance=None, observed="o2", thumb_ref=None),
    ])
    before = _snapshot(case)  # CANDIDATE_REVIEW — 아직 최초 선택 전

    with pytest.raises(InvalidTransition):
        correction.reselect_candidate(case, "c2")

    assert _snapshot(case) == before


def test_reselect_from_ready_starts_new_draft():
    """#173 E-4: 결과(READY) 화면에서도 다른 후보를 고를 수 있다. 새 selection context·새 초안이라
    EVIDENCE_REVIEW로 돌아가고, 이전 초안의 최종 검토(USER_REVIEWED)는 새 초안에 쓰지 않는다."""
    case = _case_at_evidence_review()
    case.mark_ready(report_package={"package_ref": {"kind": "report_package", "ref": "pkg_test_001"}})
    case.mark_reviewed()
    rev_before, sel_before = case.case_rev, case.selection_rev

    record = correction.reselect_candidate(case, "c2")

    assert record["kind"] == "OTHER_CANDIDATE"
    assert case.stage == "EVIDENCE_REVIEW"
    assert case.user_reviewed is False
    assert [c.candidate_id for c in case.candidates if c.selected] == ["c2"]
    assert case.selection_rev == sel_before + 1
    assert case.case_rev == rev_before + 1


# ── supersede chain (correction-record/v1.1 `supersedes_ref`) ───────────────


def test_supersede_chain_uses_contract_ref_and_evidence_accepts_it():
    """같은 필드를 한 선택 안에서 두 번 고치면 두 번째가 첫 번째를 `supersedes_ref`로 가리킨다.
    예전엔 `supersedes_id`(문자열)로 적어 evidence가 chain을 못 읽고 두 기록을 모두 head로 봐
    `multiple correction heads`로 실패했다(#173)."""
    from daesingo.evidence.corrections import correction_heads

    case = _case_at_evidence_review()
    first = correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="12가3456", new_value="12가3457",
    )
    second = correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="12가3457", new_value="12가3458",
    )

    assert first["supersedes_ref"] is None
    assert second["supersedes_ref"] == {"kind": "correction_record", "ref": first["correction_id"]}
    assert "supersedes_id" not in second
    heads = correction_heads(case.correction_records, case_id=case.case_id, selection_rev=case.selection_rev)
    assert heads["vehicle_number"]["correction_id"] == second["correction_id"]


def test_candidate_bound_chain_restarts_in_new_selection():
    """#173 E-1: 후보에 종속된 값의 정정은 선택 context 안에서만 잇는다 — 새 후보의 첫 정정은
    이전 후보의 정정을 supersede하지 않는다."""
    case = _case_at_evidence_review()
    correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="12가3456", new_value="12가3457",
    )
    case.candidates.append(Candidate(candidate_id="c9", at=None, at_provenance=None, observed="obs9", thumb_ref="fr9"))
    correction.reselect_candidate(case, "c9")

    fresh = correction.apply_correction(
        case, kind="PLATE_MANUAL_EDIT", target_field="vehicle_number",
        previous_value="34나5678", new_value="34나5679",
    )

    assert fresh["supersedes_ref"] is None


# ── 무변경 정정(correction-record §8-7) ─────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "target_field", "value"),
    [
        ("EVENT_TIME_MANUAL", "occurred_at", "2026-08-24T18:05:12+09:00"),
        ("PLATE_MANUAL_EDIT", "vehicle_number", "12가3456"),
        ("REPORT_TYPE_CHANGE", "event.safety_report_type", "TRAFFIC_VIOLATION"),
    ],
)
def test_apply_correction_with_no_actual_change_creates_nothing(kind, target_field, value):
    """§8-7: `new_value`가 `previous_value`와 같으면 CorrectionRecord를 만들지 않는다. 예전엔 기록하고
    `case_rev`를 올려, evidence가 조립할 때 `a correction must change the value`로 거부했다 — 기록은
    되돌리지 않으므로(§8-9) 그 case는 이후 CaseView를 만들 수 없었다(orchestration 러너로 발견)."""
    case = _case_at_evidence_review()
    rev_before = case.case_rev

    record = correction.apply_correction(
        case, kind=kind, target_field=target_field, previous_value=value, new_value=value,
    )

    assert record is None
    assert case.correction_records == []
    assert case.case_rev == rev_before
