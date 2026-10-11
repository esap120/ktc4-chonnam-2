"""프레임 합의 — 문자열 다수결과 대표 프레임 선택."""
from daesingo.readout import api, invariants, providers
from daesingo.readout.contracts import InputRef

REQUEST = api.ReadRequest(
    case_id="case_test",
    candidate_id="candidate_test",
    input_ref=InputRef("clip_test", "readout-native", "SOURCE_DERIVED_INCIDENT_CLIP"),
)


class Frames(providers.OcrProvider):
    """`(text, confidence)` 목록을 프레임별 판독으로 돌려준다."""

    def __init__(self, readings):
        self._readings = readings

    def read_plate(self, input_ref, target_hint):
        return providers.PlateReading(
            association=providers.AssociationReading(
                "LOW_CONFIDENCE", False, None, "FALLBACK_ONLY", []),
            frames=[
                providers.PlateFrameReading(
                    f"fr_{i}", [10 * i, 0, 80, 30], text, confidence,
                    {"plate_px_height": 30, "sharpness": 1.0})
                for i, (text, confidence) in enumerate(self._readings)
            ],
        )


def read(*readings):
    _, plate = api.read_plate(REQUEST, provider=Frames(list(readings)))
    return plate


def test_majority_of_three_or_more_frames_is_consensus():
    plate = read(("12가3456", 0.9), ("12가3456", 0.9), ("12가3456", 0.9), ("34나5678", 0.99))
    assert (plate.observation.value, plate.observation.status) == ("12가3456", "OK")
    assert plate.consensus.disagree_positions == []


def test_best_frame_comes_from_agreeing_frames_only():
    # 옆 차량을 읽은 소수 프레임의 신뢰도가 더 높아도 대표 근거가 되지 않는다.
    plate = read(("12가3456", 0.9), ("34나5678", 0.99), ("12가3456", 0.8), ("12가3456", 0.7))
    assert plate.best_frame.frame_ref == "fr_0"


def test_two_to_one_is_not_a_majority():
    plate = read(("12가3456", 0.9), ("12가3456", 0.9), ("12가3457", 0.9))
    assert plate.abstain_reason == "FRAME_DISAGREEMENT"
    assert plate.observation.value == "12가345?"


def test_extra_leading_char_is_outvoted_not_aligned():
    # 테두리를 글자로 읽어 한 자리 더 붙은 프레임은 자리를 밀지 않고 표에서 진다.
    plate = read(*[("12가3456", 0.9)] * 3, ("112가3456", 0.95))
    assert (plate.observation.value, plate.observation.status) == ("12가3456", "OK")


def test_output_still_satisfies_invariants():
    for plate in (read(("12가3456", 0.9), ("12가3456", 0.9), ("12가3457", 0.9)),
                  read(*[("12가3456", 0.9)] * 4, ("34나5678", 0.9))):
        assert invariants.check_plate(type("F", (), {"plate_readouts": [plate]})) == []
