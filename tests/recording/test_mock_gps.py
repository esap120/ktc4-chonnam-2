import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from daesingo.recording import RecordingFixture, RecordingService, load_recording_fixture

ROOT = Path(__file__).resolve().parents[2] / "data/mock/recording"


def raw(name="scenario_happy_001"):
    return json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("score", [-0.001, 1.001])
def test_confidence_outside_contract_range_is_rejected(score):
    data = raw()
    data["gps_observations"][0]["confidence"] = {"score": score, "metric": "test"}
    with pytest.raises(ValueError):
        RecordingFixture.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("score", [0.0, 1.0])
def test_confidence_contract_endpoints_are_preserved(score):
    data = raw()
    data["gps_observations"][0]["confidence"] = {"score": score, "metric": "test"}
    fixture = RecordingFixture.model_validate_json(json.dumps(data))
    with RecordingService.from_fixture(fixture) as service:
        assert service.list_gps_observations()[0].confidence.score == score


@pytest.mark.parametrize("run_ref", [
    {"kind": "analysis_run", "ref": "run_test"},
    {"kind": "readout_run", "ref": "run_test"},
    None,
])
def test_recording_gps_rejects_any_explicit_run_ref(run_ref):
    data = raw()
    data["gps_observations"][0]["produced_by"]["run_ref"] = run_ref
    with pytest.raises(ValueError):
        RecordingFixture.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("name", ["scenario_happy_001", "scenario_unknown_abstain_partial_001"])
def test_public_gps_preserves_existing_json(name):
    fixture = load_recording_fixture(name)
    with RecordingService.from_fixture(fixture) as service:
        observations = service.list_gps_observations()
        assert [o.model_dump(exclude_unset=True) for o in observations] == raw(name)["gps_observations"]
        if name == "scenario_happy_001":
            assert observations[0].source.ref.ref in {s.media_stream_ref for s in fixture.media_streams}
        else:
            assert observations[0].value is None and observations[0].status == "UNKNOWN"
            assert observations[0].reason.code == "recording.gps.source_absent"


def test_missing_gps_is_empty_not_unknown():
    missing = [p for p in ROOT.glob("*.json") if "gps_observations" not in json.loads(p.read_text(encoding="utf-8"))]
    assert len(missing) == 5
    for path in missing:
        fixture = load_recording_fixture(path.stem)
        assert fixture.gps_observations == []
        assert RecordingService.from_fixture(fixture).list_gps_observations() == []


@pytest.mark.parametrize("status,has_value,valid", [
    ("OK", True, True), ("OK", False, False),
    ("NEEDS_REVIEW", True, True), ("NEEDS_REVIEW", False, True),
    ("UNKNOWN", False, True), ("UNKNOWN", True, False),
    ("ERROR", False, True), ("ERROR", True, False),
    ("NOT_APPLICABLE", False, True), ("NOT_APPLICABLE", True, False)])
def test_status_value_invariants(status, has_value, valid):
    from daesingo.recording import GPSObservation
    data = raw()["gps_observations"][0]
    data["status"] = status
    if not has_value: data["value"] = None
    if valid: GPSObservation.model_validate(data)
    else:
        with pytest.raises(ValueError): GPSObservation.model_validate(data)


@pytest.mark.parametrize("bad", ["lat", "lon", "nan", "inf", "bool", "string", "lng", "source", "kind", "duplicate", "extra",
    "missing_value", "missing_source_ref", "producer", "version", "confidence"])
def test_bad_gps_fixture_is_rejected(bad):
    data = raw()
    gps = data["gps_observations"][0]
    if bad == "lat": gps["value"]["lat"] = 91.
    if bad == "lon": gps["value"]["lon"] = -181.
    if bad == "nan": gps["value"]["lat"] = float("nan")
    if bad == "inf": gps["value"]["lon"] = float("inf")
    if bad == "bool": gps["value"]["lat"] = True
    if bad == "string": gps["value"]["lon"] = "126.8515"
    if bad == "lng": gps["value"]["lng"] = gps["value"].pop("lon")
    if bad == "source": gps["source"]["ref"]["ref"] = "not-registered"
    if bad == "kind": gps["source"]["ref"]["kind"] = "source_asset"
    if bad == "duplicate": data["gps_observations"].append(gps.copy())
    if bad == "extra": gps["value"]["unexpected"] = 1
    if bad == "missing_value": del gps["value"]
    if bad == "missing_source_ref": del gps["source"]["ref"]
    if bad == "producer": gps["produced_by"]["module"] = "search"
    if bad == "version": gps["contract_version"] = "unsupported"
    if bad == "confidence": gps["confidence"] = {"score": 0.5}
    with pytest.raises(ValueError): RecordingFixture.model_validate_json(json.dumps(data))


def test_returns_and_input_are_isolated_and_revalidated():
    fixture = load_recording_fixture("scenario_happy_001")
    service = RecordingService.from_fixture(fixture)
    expected = service.list_gps_observations()[0].model_dump()
    first = service.list_gps_observations()
    first[0].support_refs.clear()
    first.clear()
    fixture.gps_observations[0].support_refs.clear()
    assert service.list_gps_observations()[0].model_dump() == expected
    fixture.gps_observations.append(fixture.gps_observations[0])
    with pytest.raises(ValueError): RecordingService.from_fixture(fixture)


def test_repository_revalidates_and_rejects_duplicate_and_tampering():
    from daesingo.recording.repository import InMemoryRecordingRepository
    fixture = load_recording_fixture("scenario_happy_001")
    repository = InMemoryRecordingRepository()
    observation = fixture.gps_observations[0]
    with pytest.raises(ValueError): repository.add_gps_observation(observation)
    for stream in fixture.media_streams: repository.add_media_stream(stream)
    repository.add_gps_observation(observation)
    with pytest.raises(ValueError): repository.add_gps_observation(observation)
    tampered = observation.model_copy(update={"status": "UNKNOWN"})
    with pytest.raises(ValueError): repository.add_gps_observation(tampered)
    fixture.gps_observations[0] = tampered
    with pytest.raises(ValueError): RecordingService.from_fixture(fixture)
    observation.support_refs.clear()
    returned = repository.list_gps_observations()
    assert returned[0].support_refs
    returned[0].support_refs.clear()
    assert repository.list_gps_observations()[0].support_refs


def test_current_evidence_coordinate_input_is_compatible():
    from daesingo.evidence.assembly import _location
    with RecordingService.from_fixture(load_recording_fixture("scenario_happy_001")) as service:
        gps = service.list_gps_observations()[0].model_dump(exclude_unset=True)
        location = _location(case_id="gps-fixture-test", location_hint=None, gps_observation=gps)
        assert location["coord"]["value"] == gps["value"]


def test_mutation_of_default_empty_list_is_not_silently_discarded():
    data = raw()
    del data["gps_observations"]
    fixture = RecordingFixture.model_validate_json(json.dumps(data))
    observation = load_recording_fixture("scenario_happy_001").gps_observations[0]
    fixture.gps_observations.extend([observation, observation])
    with pytest.raises(ValueError): RecordingService.from_fixture(fixture)
    fixture.gps_observations.pop()
    assert RecordingService.from_fixture(fixture).list_gps_observations() == [observation]


@pytest.mark.parametrize("target,location", [
    ("observation", ("unexpected",)),
    ("producer", ("produced_by", "run_ref")),
    ("coordinate", ("value", "unexpected")),
])
def test_repository_rejects_undeclared_fields_in_tampered_gps_models(target, location):
    from daesingo.recording.repository import InMemoryRecordingRepository

    fixture = load_recording_fixture("scenario_happy_001")
    repository = InMemoryRecordingRepository()
    for stream in fixture.media_streams:
        repository.add_media_stream(stream)
    observation = fixture.gps_observations[0]
    if target == "observation":
        tampered = observation.model_copy(update={"unexpected": "test"})
    elif target == "producer":
        producer = observation.produced_by.model_copy(update={
            "run_ref": {"kind": "analysis_run", "ref": "run_test"},
        })
        tampered = observation.model_copy(update={"produced_by": producer})
    else:
        coordinate = observation.value.model_copy(update={"unexpected": "test"})
        tampered = observation.model_copy(update={"value": coordinate})

    with pytest.raises(ValidationError) as caught:
        repository.add_gps_observation(tampered)
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == location
        for error in caught.value.errors(include_input=False)
    )
    assert repository.list_gps_observations() == []
