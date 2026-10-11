"""#239 — `resolve_independent_facts()`는 `assemble_evidence()`와 같은 규칙으로 상황 독립 값만 만든다.

Fine `UNCERTAIN` + 응답 전(`AWAIT_SITUATION_RESPONSE`)에는 EvidenceRecord를 만들지 않는다(ADR-EVIDENCE-009
§2.1). 그래도 case가 번호판 · 시각 · 위치를 부분 투영할 수 있도록, evidence가 그 세 필드만 같은 규칙으로
계산해 준다. 여기서는 ① 반환값이 EvidenceRecord가 아니고 ② 응답 뒤 조립한 Record의 같은 필드와 일치하며
③ 결정할 수 없는 값은 만들지 않는다는 것을 확인한다.
"""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from daesingo.evidence import (
    AWAIT_SITUATION_RESPONSE,
    ContractInputError,
    assemble_evidence,
    classify_visual_evidence,
    resolve_independent_facts,
    resolve_time,
)

ROOT = Path(__file__).resolve().parents[2]
_FIELDS = ("occurred_at", "vehicle_number", "location")
_RECORD_ONLY = ("record_ref", "case_ref", "selection_rev", "basis", "event", "provenance", "situation_response")


def _load(module: str) -> dict:
    return json.loads((ROOT / f"data/mock/{module}/scenario_happy_001.json").read_text(encoding="utf-8"))


class IndependentFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        recording, search, readout, case = (_load(m) for m in ("recording", "search", "readout", "case"))
        cls.candidate = next(
            item for group in search["analysis_run_candidate_events"] for item in group["candidates"]
            if item["candidate_id"] == "candidate_h001"
        )
        visual = next(item for item in search["visual_evidences"] if item["candidate_id"] == "candidate_h001")
        cls.uncertain = dict(visual, verification="UNCERTAIN", visual_event_type=None)
        cls.time_sources = recording["time_source_candidates"]
        cls.overlay = readout["overlay_time_readouts"][0]
        cls.plate = readout["plate_readouts"][0]
        cls.clip = recording["incident_clips"][0]
        cls.location_hint = case["case_views"][-1]["hints"]["location"]

    def _time(self, corrections=()):
        return resolve_time(
            time_source_candidates=self.time_sources, overlay_time_readout=self.overlay,
            candidate_event=self.candidate, correction_records=list(corrections),
            case_id="case_h001", selection_rev=1, resolution_id="tr_facts_unit",
        )

    def _facts(self, corrections=(), *, plate="default", time=None, location_hint="default"):
        return resolve_independent_facts(
            case_id="case_h001", selection_rev=1,
            time_resolution=time if time is not None else self._time(corrections),
            plate_readout=self.plate if plate == "default" else plate,
            location_hint=self.location_hint if location_hint == "default" else location_hint,
            correction_records=list(corrections),
        )

    def _assemble_after_unsure(self, corrections=()):
        """같은 관찰 입력에 사용자가 「잘 모르겠어요」로 답한 뒤의 조립."""
        return assemble_evidence(
            case_id="case_h001", selection_rev=1, candidate_event=self.candidate,
            visual_evidence=self.uncertain, time_resolution=self._time(corrections),
            plate_readout=self.plate, incident_clip=self.clip, record_id="er_facts_unit",
            location_hint=self.location_hint, correction_records=list(corrections),
            situation_response={"value": "USER_UNSURE", "responded_at": "2026-09-13T10:00:00+09:00", "candidate_ref": None},
        )

    def _correction(self, correction_id, target, previous, new, kind):
        return {
            "contract_version": "correction-record/v1.1", "correction_id": correction_id,
            "case_id": "case_h001", "selection_rev": 1, "kind": kind, "target_field": target,
            "previous_value": previous, "new_value": new, "supersedes_ref": None,
            "corrected_at": "2026-09-13T10:00:00+09:00",
        }

    def test_awaiting_response_yields_facts_but_not_a_record(self):
        self.assertEqual(AWAIT_SITUATION_RESPONSE, classify_visual_evidence(self.uncertain, None).decision)
        facts = self._facts()

        self.assertEqual(set(_FIELDS), set(facts))
        for key in _RECORD_ONLY:
            self.assertNotIn(key, facts)
        self.assertEqual("12가3456", facts["vehicle_number"]["value"])
        # 응답 전 조립은 여전히 막혀 있다 — resolver가 그 시점을 앞당기지 않는다.
        with self.assertRaisesRegex(ContractInputError, "USER_UNSURE"):
            assemble_evidence(
                case_id="case_h001", selection_rev=1, candidate_event=self.candidate,
                visual_evidence=self.uncertain, time_resolution=self._time(), plate_readout=self.plate,
                incident_clip=self.clip, record_id="er_facts_unit", location_hint=self.location_hint,
            )

    def test_facts_match_the_record_assembled_after_the_response(self):
        record = self._assemble_after_unsure()
        self.assertEqual({key: record[key] for key in _FIELDS}, self._facts())

    def test_corrections_apply_by_the_same_rules(self):
        corrections = [
            self._correction("corr_plate", "vehicle_number", "12가3456", "55나5555", "PLATE_MANUAL_EDIT"),
            self._correction("corr_place", "location.place_name", None, "수정 장소", "REPORT_TYPE_CHANGE"),
            self._correction("corr_coord", "location.coord", {"lat": 35.1, "lon": 126.1}, {"lat": 35.2, "lon": 126.2}, "REPORT_TYPE_CHANGE"),
            self._correction("corr_time", "occurred_at", "2026-08-24T18:21:44+09:00", "2026-08-24T18:22:00+09:00", "EVENT_TIME_MANUAL"),
        ]
        facts = self._facts(corrections)
        record = self._assemble_after_unsure(corrections)

        self.assertEqual({key: record[key] for key in _FIELDS}, facts)
        self.assertEqual("55나5555", facts["vehicle_number"]["value"])
        self.assertTrue(facts["vehicle_number"]["user_corrected"])
        self.assertEqual("수정 장소", facts["location"]["place_name"]["value"])
        self.assertEqual("2026-08-24T18:22:00+09:00", facts["occurred_at"]["value"])
        self.assertTrue(facts["occurred_at"]["user_corrected"])

    def test_situation_dependent_corrections_are_ignored(self):
        change = self._correction("corr_report", "event.safety_report_type", "TRAFFIC_VIOLATION", "MOTORCYCLE_VIOLATION", "REPORT_TYPE_CHANGE")
        self.assertEqual(self._facts(), self._facts([change]))

    def test_time_correction_must_be_selected_by_the_time_resolution(self):
        correction = self._correction("corr_time", "occurred_at", "2026-08-24T18:21:44+09:00", "2026-08-24T18:22:00+09:00", "EVENT_TIME_MANUAL")
        with self.assertRaisesRegex(ContractInputError, "selected by TimeResolution"):
            self._facts([correction], time=self._time())

    def test_undeterminable_values_are_left_out(self):
        abstained = dict(self.plate, abstained=True)
        unknown_time = resolve_time(
            time_source_candidates=[], overlay_time_readout=None, candidate_event=self.candidate,
            case_id="case_h001", selection_rev=1, resolution_id="tr_facts_unknown",
        )
        self.assertEqual({}, self._facts(plate=abstained, time=unknown_time, location_hint=None))
        self.assertEqual({}, self._facts(plate=None, time=unknown_time, location_hint="  "))

    def test_inputs_are_not_mutated(self):
        corrections = [self._correction("corr_plate", "vehicle_number", "12가3456", "55나5555", "PLATE_MANUAL_EDIT")]
        time = self._time()
        before = deepcopy((time, self.plate, corrections))
        facts = self._facts(corrections, time=time)
        facts["occurred_at"]["time_resolution_ref"]["ref"] = "changed"
        self.assertEqual(before, (time, self.plate, corrections))


if __name__ == "__main__":
    unittest.main()
