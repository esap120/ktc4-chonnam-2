"""Pure EvidenceRecord and EvidenceNeeds assembly."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ._contract import Contract, contract_ref, parse_rfc3339, require
from .corrections import correction_heads
from .disposition import NOT_ASSEMBLED, classify_visual_evidence
from .errors import VisualEventNotAssembled
from .policy import EVIDENCE_POLICY_REF, GENERIC_VIOLATION_EXPRESSION, event_policy

_TIME_LABELS = {
    "readout.overlay_ocr": "time.source.overlay_ocr",
    "recording.filename_time": "time.source.filename_time",
    "recording.file_metadata_time": "time.source.file_metadata",
    "recording.manufacturer_metadata_time": None,
    "case.user_correction": "time.source.user_correction",
}


def _evidence_value(
    value: Any,
    *,
    source_kind: str,
    source_ref: Contract,
    observability: str,
    label_key: str | None,
    support_refs: list[Contract],
    user_corrected: bool = False,
    needs_review: bool = False,
) -> Contract:
    require(observability in {"OBSERVED", "INFERRED"}, "invalid evidence observability")
    require(not (user_corrected and needs_review), "a corrected value cannot need review")
    require(not (value is None and needs_review), "a null value cannot need review")
    return {
        "value": deepcopy(value),
        "source": {
            "kind": source_kind,
            "ref": deepcopy(source_ref),
            "observability": observability,
            "label_key": label_key,
        },
        "support_refs": deepcopy(support_refs),
        "user_corrected": user_corrected,
        "needs_review": needs_review,
    }


def _validate_context(
    *,
    case_id: str,
    candidate_event: Contract,
    visual_evidence: Contract,
    plate_readout: Contract | None,
    incident_clip: Contract,
) -> None:
    candidate_id = candidate_event.get("candidate_id")
    require(candidate_id == visual_evidence.get("candidate_id"), "CandidateEvent and VisualEvidence mismatch")
    if plate_readout:
        require(candidate_id == plate_readout.get("candidate_id"), "CandidateEvent and PlateReadout mismatch")
        require(case_id == plate_readout.get("case_id"), "case_id and PlateReadout mismatch")
        require(
            plate_readout.get("input_ref", {}).get("incident_clip_ref") == incident_clip.get("incident_clip_ref"),
            "PlateReadout does not reference the supplied IncidentClip",
        )
    candidate_span = candidate_event.get("span") or {}
    clip_provenance = incident_clip.get("source_provenance") or {}
    clip_timeline = clip_provenance.get("timeline_ref") or {}
    require(
        candidate_span.get("timeline_id") == clip_timeline.get("timeline_id"),
        "CandidateEvent and IncidentClip timeline_id mismatch",
    )
    require(
        candidate_span.get("timeline_revision") == clip_timeline.get("revision"),
        "CandidateEvent and IncidentClip timeline revision mismatch",
    )
    requested = clip_provenance.get("requested_range") or {}
    require("start_sec" in requested and "end_sec" in requested, "IncidentClip requested_range is required")


def _event_values(visual_evidence: Contract, situation_response: Contract | None) -> Contract:
    visual_ref = contract_ref("visual_evidence", visual_evidence["visual_evidence_id"])
    verification = visual_evidence.get("verification")
    visual_type = visual_evidence.get("visual_event_type")
    require(verification in {"OBSERVED", "NOT_OBSERVED", "UNCERTAIN"}, "invalid VisualEvidence verification")
    require((verification == "OBSERVED") == (visual_type is not None), "VisualEvidence value/verification mismatch")

    if visual_type is None:
        require(verification == "UNCERTAIN", "only an UNCERTAIN VisualEvidence may produce a null visual event")
        require(
            situation_response is not None and situation_response.get("value") == "USER_UNSURE",
            "an uncertain event requires USER_UNSURE context for the v1 fallback",
        )
        report_type = "MOTORCYCLE_VIOLATION" if visual_evidence.get("target", {}).get("described_as", "").find("이륜차") >= 0 else "TRAFFIC_VIOLATION"
        expression = GENERIC_VIOLATION_EXPRESSION
        report_needs_review = True
        visual_source_kind = "evidence.category_mapping"
        visual_observability = "INFERRED"
        visual_label = None
    else:
        mapped = event_policy(visual_type)
        report_type = mapped["safety_report_type"]
        expression = mapped["violation_expression"]
        report_needs_review = False
        visual_source_kind = "search.visual_inference"
        visual_observability = "OBSERVED"
        visual_label = "event.source.visual_inference"

    support = [visual_ref]
    return {
        "visual_event_type": _evidence_value(
            visual_type,
            source_kind=visual_source_kind,
            source_ref=visual_ref,
            observability=visual_observability,
            label_key=visual_label,
            support_refs=support,
        ),
        "safety_report_type": _evidence_value(
            report_type,
            source_kind="evidence.category_mapping",
            source_ref=visual_ref,
            observability="INFERRED",
            label_key="event.source.category_mapping",
            support_refs=support,
            needs_review=report_needs_review,
        ),
        "violation_expression": _evidence_value(
            expression,
            source_kind="evidence.violation_expression",
            source_ref=visual_ref,
            observability="INFERRED",
            label_key="event.source.violation_expression",
            support_refs=support,
        ),
    }


def _location(
    *, case_id: str, location_hint: str | None, gps_observation: Contract | None
) -> Contract | None:
    location: Contract = {}
    if isinstance(location_hint, str) and location_hint.strip():
        case_ref = contract_ref("case", case_id)
        location["user_hint"] = _evidence_value(
            location_hint.strip(),
            source_kind="case.user_location_hint",
            source_ref=case_ref,
            observability="OBSERVED",
            label_key="location.source.user_hint",
            support_refs=[],
            user_corrected=True,
        )
    if gps_observation:
        status = gps_observation.get("status")
        value = gps_observation.get("value")
        if status == "OK" and isinstance(value, dict):
            require(isinstance(value.get("lat"), (int, float)), "GPS latitude is required")
            require(isinstance(value.get("lon"), (int, float)), "GPS longitude is required")
            source = gps_observation.get("source") or {}
            source_ref = source.get("ref")
            require(isinstance(source_ref, dict), "GPS source ref is required for an OK value")
            location["coord"] = _evidence_value(
                value,
                source_kind=source.get("kind"),
                source_ref=source_ref,
                observability="OBSERVED",
                label_key="location.source.gps",
                support_refs=gps_observation.get("support_refs") or [],
            )
        else:
            require(value is None, "non-OK GPS observation cannot carry a coordinate")
    return location or None


def _independent_facts(
    *,
    case_id: str,
    time_resolution: Contract,
    plate_readout: Contract | None,
    location_hint: str | None,
    gps_observation: Contract | None,
    heads: dict[str, Contract],
) -> Contract:
    facts: Contract = {}
    resolution_ref = time_resolution.get("resolution_ref")
    require(isinstance(resolution_ref, dict), "TimeResolution.resolution_ref is required")
    resolved = time_resolution.get("resolved")
    if time_resolution.get("status") == "UNKNOWN":
        require(resolved is None, "UNKNOWN TimeResolution cannot have resolved")
    else:
        require(isinstance(resolved, dict), "resolved TimeResolution is required")
        source_kind = resolved["source"]["kind"]
        facts["occurred_at"] = {
            "value": resolved["value"],
            "time_resolution_ref": deepcopy(resolution_ref),
            "resolution_status": time_resolution["status"],
            "user_corrected": resolved["user_corrected"],
            "source": {"kind": source_kind, "label_key": _TIME_LABELS.get(source_kind)},
        }

    if plate_readout:
        plate_ref = contract_ref("plate_readout", plate_readout["readout_id"])
        observation = plate_readout.get("observation") or {}
        value = observation.get("value")
        if not plate_readout.get("abstained") and observation.get("status") == "OK" and value:
            require(isinstance(value, str), "an accepted plate value must be a string")
            facts["vehicle_number"] = _evidence_value(
                value,
                source_kind="readout.plate_ocr",
                source_ref=plate_ref,
                observability="OBSERVED",
                label_key="plate.source.plate_ocr",
                support_refs=[plate_ref],
            )

    location = _location(case_id=case_id, location_hint=location_hint, gps_observation=gps_observation)
    if location:
        facts["location"] = location

    for target, correction in heads.items():
        if target == "occurred_at":
            selected = time_resolution.get("provenance", {}).get("selected_input_ref")
            require(
                selected == contract_ref("correction_record", correction["correction_id"]),
                "occurred_at correction must be selected by TimeResolution",
            )
            continue
        if target != "vehicle_number" and not target.startswith("location."):
            continue
        corrected_ref = contract_ref("correction_record", correction["correction_id"])
        corrected = _evidence_value(
            correction["new_value"],
            source_kind="case.user_correction",
            source_ref=corrected_ref,
            observability="OBSERVED",
            label_key=None,
            support_refs=[corrected_ref],
            user_corrected=True,
        )
        if target == "vehicle_number":
            facts["vehicle_number"] = corrected
        else:
            facts.setdefault("location", {})[target.split(".", 1)[1]] = corrected
    return facts


def resolve_independent_facts(
    *,
    case_id: str,
    selection_rev: int,
    time_resolution: Contract,
    plate_readout: Contract | None,
    location_hint: str | None = None,
    gps_observation: Contract | None = None,
    correction_records: list[Contract] | None = None,
) -> Contract:
    """Resolve the situation-independent EvidenceRecord fields without assembling a Record.

    Returns only `occurred_at` · `vehicle_number` · `location`, each in the exact
    EvidenceRecord shape and omitted under the same rules.  `assemble_evidence()` fills
    those three fields through this same resolution, so a caller that cannot assemble
    yet (Fine `UNCERTAIN` awaiting the user's situation response, #239) can project them
    without re-implementing plate/time/location adoption.

    The result is not an EvidenceRecord: it carries no `record_ref`, `basis`, `event`,
    `provenance` or `situation_response`, and nothing is stored, published or derived
    from it here (ADR-EVIDENCE-009 §2.1 — no final Record before the user's response).
    """
    require(isinstance(selection_rev, int) and not isinstance(selection_rev, bool) and selection_rev >= 1, "selection_rev must be >= 1")
    return _independent_facts(
        case_id=case_id,
        time_resolution=time_resolution,
        plate_readout=plate_readout,
        location_hint=location_hint,
        gps_observation=gps_observation,
        heads=correction_heads(correction_records or [], case_id=case_id, selection_rev=selection_rev),
    )


def assemble_evidence(
    *,
    case_id: str,
    selection_rev: int,
    candidate_event: Contract,
    visual_evidence: Contract,
    time_resolution: Contract,
    plate_readout: Contract | None,
    incident_clip: Contract,
    record_id: str,
    supersedes_id: str | None = None,
    location_hint: str | None = None,
    gps_observation: Contract | None = None,
    situation_response: Contract | None = None,
    correction_records: list[Contract] | None = None,
) -> Contract:
    """Adopt upstream observations into an immutable EvidenceRecord.

    A `NOT_OBSERVED` VisualEvidence never reaches a Record — the decision belongs to
    `classify_visual_evidence()`, which the caller is expected to ask first.  This
    guard only stops a direct call from promoting that valid negative into one.
    """
    disposition = classify_visual_evidence(visual_evidence, situation_response)
    if disposition.decision == NOT_ASSEMBLED:
        raise VisualEventNotAssembled(disposition.reason_code)
    require(isinstance(selection_rev, int) and not isinstance(selection_rev, bool) and selection_rev >= 1, "selection_rev must be >= 1")
    _validate_context(
        case_id=case_id,
        candidate_event=candidate_event,
        visual_evidence=visual_evidence,
        plate_readout=plate_readout,
        incident_clip=incident_clip,
    )
    resolution_ref = time_resolution.get("resolution_ref")
    require(isinstance(resolution_ref, dict), "TimeResolution.resolution_ref is required")
    visual_ref = contract_ref("visual_evidence", visual_evidence["visual_evidence_id"])
    record: Contract = {
        "contract_version": "evidence-record/v1.3",
        "record_ref": contract_ref("evidence_record", record_id),
        "case_ref": contract_ref("case", case_id),
        "selection_rev": selection_rev,
        "basis": {
            "candidate_ref": contract_ref("candidate_event", candidate_event["candidate_id"]),
            "visual_evidence_ref": visual_ref,
            "evidence_interval_ref": contract_ref("incident_clip", incident_clip["incident_clip_ref"]),
        },
        "event": _event_values(visual_evidence, situation_response),
    }
    if supersedes_id:
        record["supersedes_ref"] = contract_ref("evidence_record", supersedes_id)

    heads = correction_heads(correction_records or [], case_id=case_id, selection_rev=selection_rev)
    # occurred_at · vehicle_number · location (with their corrections) come from the same
    # resolution `resolve_independent_facts()` exposes for the pre-response projection.
    record.update(
        _independent_facts(
            case_id=case_id,
            time_resolution=time_resolution,
            plate_readout=plate_readout,
            location_hint=location_hint,
            gps_observation=gps_observation,
            heads=heads,
        )
    )

    input_refs = [visual_ref]
    if plate_readout:
        input_refs.append(contract_ref("plate_readout", plate_readout["readout_id"]))

    visual_correction = heads.get("event.visual_event_type")
    if visual_correction is not None:
        corrected_ref = contract_ref("correction_record", visual_correction["correction_id"])
        visual_value = visual_correction["new_value"]
        if visual_correction.get("kind") == "SITUATION_CHANGE":
            require(visual_value is not None, "SITUATION_CHANGE requires a concrete visual event")
        if visual_value is None:
            require(
                visual_evidence.get("verification") == "UNCERTAIN",
                "a visual correction cannot erase an observed event without uncertain visual evidence",
            )
        record["event"]["visual_event_type"] = _evidence_value(
            visual_value,
            source_kind="case.user_correction",
            source_ref=corrected_ref,
            observability="OBSERVED",
            label_key=None,
            support_refs=[corrected_ref],
            user_corrected=True,
        )
        if visual_value is not None:
            mapped = event_policy(visual_value)
            for field in ("safety_report_type", "violation_expression"):
                if f"event.{field}" not in heads:
                    record["event"][field] = _evidence_value(
                        mapped[field],
                        source_kind="evidence.category_mapping" if field == "safety_report_type" else "evidence.violation_expression",
                        source_ref=corrected_ref,
                        observability="INFERRED",
                        label_key="event.source.category_mapping" if field == "safety_report_type" else "event.source.violation_expression",
                        support_refs=[corrected_ref],
                    )

    for target, correction in heads.items():
        if target == "event.visual_event_type" or not target.startswith("event."):
            continue
        corrected_ref = contract_ref("correction_record", correction["correction_id"])
        record["event"][target.split(".", 1)[1]] = _evidence_value(
            correction["new_value"],
            source_kind="case.user_correction",
            source_ref=corrected_ref,
            observability="OBSERVED",
            label_key=None,
            support_refs=[corrected_ref],
            user_corrected=True,
        )

    if situation_response is not None:
        value = situation_response.get("value")
        require(value in {"CONFIRMED", "CORRECTED", "USER_UNSURE"}, "invalid situation response")
        responded_at = situation_response.get("responded_at")
        parse_rfc3339(responded_at)
        candidate_ref = situation_response.get("candidate_ref")
        require(value == "USER_UNSURE" or isinstance(candidate_ref, dict), "confirmed/corrected response needs candidate_ref")
        if candidate_ref is not None:
            require(
                candidate_ref == contract_ref("candidate_event", candidate_event["candidate_id"]),
                "situation response candidate_ref does not match the selected candidate",
            )
        situation_changes = [
            item for item in heads.values() if item.get("kind") == "SITUATION_CHANGE"
        ]
        require(value != "CORRECTED" or len(situation_changes) == 1, "CORRECTED requires one SITUATION_CHANGE head")
        require(value != "USER_UNSURE" or not situation_changes, "USER_UNSURE cannot create a SITUATION_CHANGE")
        record["situation_response"] = deepcopy(situation_response)

    input_refs.append(deepcopy(resolution_ref))
    correction_refs = [contract_ref("correction_record", item["correction_id"]) for item in heads.values()]
    selected = time_resolution.get("provenance", {}).get("selected_input_ref")
    if isinstance(selected, dict) and selected.get("kind") == "correction_record" and selected not in correction_refs:
        correction_refs.append(deepcopy(selected))
    record["provenance"] = {
        "input_refs": input_refs,
        "correction_refs": correction_refs,
        "policy_ref": EVIDENCE_POLICY_REF,
    }
    return record


def calculate_evidence_needs(
    evidence_record: Contract, plate_readout: Contract | None, *, emit_empty: bool = True
) -> Contract | None:
    """Return a declarative need; this function never dispatches work."""
    items: list[Contract] = []
    if plate_readout and plate_readout.get("abstained") and "vehicle_number" not in evidence_record:
        items.append(
            {
                "kind": "PLATE_REREAD",
                "would_fill": "VEHICLE_NUMBER",
                "why": {
                    "code": "readout.plate_abstained_frame_disagreement",
                    "summary": "The plate observation was withheld because frame readings disagreed.",
                },
                "optional": False,
                "context_refs": [
                    {"role": "evidence.interval", "ref": deepcopy(evidence_record["basis"]["evidence_interval_ref"])},
                    {"role": "evidence.target_hint", "ref": deepcopy(evidence_record["basis"]["visual_evidence_ref"])},
                ],
            }
        )
    if not items and not emit_empty:
        return None
    return {
        "contract_version": "evidence-needs/v1",
        "basis_record_ref": deepcopy(evidence_record["record_ref"]),
        "items": items,
    }
