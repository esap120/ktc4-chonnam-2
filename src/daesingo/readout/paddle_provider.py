"""실제 OCR provider — PaddleOCR로 프레임 픽셀을 글자로 바꾼다.

`providers.py`의 `FixtureOcrProvider`와 같은 자리에 들어간다. 공개 함수(`api.py`)는
손대지 않는다 — provider가 하는 일은 프레임을 받아 글자·신뢰도·overlay 유무까지 말하는
것뿐이고, 판정과 계약 조립은 전부 `api.py`가 한다.

## 프레임을 어디서 받나 — 여기서 정하지 않는다

`frame_source`로 주입받는다(`.frames(clip_ref)` 하나만 있으면 된다).
**`frame_ref`를 이 모듈이 만들지 않기 위해서다** — `FrameRef`는 `recording`이 발급하고
readout은 보존만 한다(`contract-plate-overlay-readout.md` §「`frame_ref` 형식」).

독립 실험에는 `LocalVideoFrameSource`를 쓴다. 이 경로의 **`frame_ref`는 임시값이다.**
실제 IncidentClip에는 `RecordingFrameSource`를 쓴다. 이 경로는 recording의
`resolve_frame`/`read_frame`을 통해 발급된 ref와 PNG를 그대로 받는다.

## 측정 근거

필터 기준은 `experiments/ocr-baseline-2026-09-15` 실행에서 가져왔다. **목표치가 아니라
그때 돌던 값**이고, 실측이 쌓이면 Technical Spec에서 확정한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite

from daesingo.recording import RecordingCapabilityError

from .providers import (
    PRESENT,
    UNDETERMINED,
    AssociationReading,
    IncidentClipFrames,
    OcrProvider,
    OverlayReading,
    OverlaySampleReading,
    PlateFrameReading,
    PlateReading,
    ProviderError,
)

SAMPLE_RATIOS = (0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)
"""clip 길이 대비 샘플 지점. 7점인 이유 — 번호판 합의는 같은 문자열 3장 이상 + 과반이어야
하므로(`api.MIN_AGREEING_FRAMES`) 3장이면 한 장만 놓쳐도 합의가 깨진다. 양 끝 20%를 빼는 것은
구간 경계에서 대상이 막 들어오거나 나가는 프레임을 피하려는 것이다. overlay 검증은 2점 이상이면
성립하므로 그대로 쓴다."""

MIN_DIGITS = 3
MIN_ASPECT = 2.2
"""번호판 영역의 최소 가로세로비. 1줄 기준이다 — 2줄은 검출 박스가 아랫줄만 감싸므로
여기서도 1줄처럼 보인다(baseline §① bbox 미결)."""

PLATE_PATTERN = re.compile(r"\d{2,3}[가-힣]\d{4}")
"""1줄 형식. 맞는 후보를 **우선**하지만 안 맞는다고 버리지 않는다 — 2줄 아랫줄(`바5215`)."""

DIGITS_ONLY_PLATE = re.compile(r"\d{2,3}\s?\d{4}")
"""대상 차량 crop 안에서 한글만 빠진 1줄 번호판 OCR 결과.

전체 화면에서는 overlay 숫자 줄을 번호판으로 오인할 수 있어 쓰지 않는다.
"""

HANGUL = re.compile(r"[가-힣]")
"""번호판 문자열은 한글(용도·지역 문자)을 포함한다.

**이 조건이 overlay 줄을 걸러낸다.** `20260806_061434_EVT_1` 실측에서 번호판이 하나도
검출되지 않자 화면 하단 overlay(`2026/08/06 06:14:34 13.80 X:+0.062 ...`)가 숫자·가로세로비
필터를 통과해 번호판 후보로 올라왔다. 그 영상은 프레임마다 시각이 달라 보류됐지만,
**시각이 같았다면 overlay 문자열이 `status=OK`로 확정된다.**

한글이 빠진 오인식(baseline 백색 1줄의 `2354874`)도 후보가 아니게 된다. 그것은 어차피 틀린
판독이고, 틀린 후보를 하나 잃는 쪽이 overlay를 번호판으로 확정하는 것보다 싸다."""

TIMESTAMP_PATTERN = re.compile(r"\d{4}[-/.]\d{2}[-/.]\d{2}")
"""overlay 줄을 **찾는** 패턴. 날짜가 보이면 줄 전체를 `raw_text`로 넘긴다 — 시각만 떼는 것은
`api.py._parse_overlay_text()`의 일이다(PR #81). 실물은 같은 줄에 속도·G센서가 붙어 오므로
여기서 자르면 그 정보가 사라진다."""


@dataclass
class SourceFrame:
    """판독할 프레임 한 장. `frame_ref`는 공급자가 준 것을 그대로 쓴다."""
    frame_ref: str
    offset_sec: float
    image: object


@dataclass
class TextBox:
    """OCR이 돌려준 줄 하나. `box`는 (x1, y1, x2, y2)."""
    text: str
    score: float
    box: tuple

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def _hint_bbox(target_hint, frame_ref):
    """해당 프레임에 붙은 대상 차량 영역만 돌려준다.

    한 프레임의 bbox를 다른 시점에 재사용하면 옆 차량을 읽을 수 있으므로, frame_ref가
    일치할 때만 crop한다. 추적기가 frame별 hint를 공급하면 각 프레임에서 같은 경로를 탄다.
    """
    if target_hint is None or getattr(target_hint, "frame_ref", None) != frame_ref:
        return None
    bbox = getattr(target_hint, "bbox_xywh", None)
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    if not all(isinstance(value, int) for value in bbox):
        return None
    x, y, width, height = bbox
    return (x, y, width, height) if width > 0 and height > 0 else None


def _target_crop(image, target_hint, frame_ref):
    """대상 차량 crop을 3배로 키운 이미지와 원본 좌표 변환값을 반환한다."""
    bbox = _hint_bbox(target_hint, frame_ref)
    if bbox is None:
        return None
    import cv2

    x, y, width, height = bbox
    pad = max(8, round(max(width, height) * 0.10))
    x1, y1 = max(0, x - pad), max(0, y - pad)
    x2 = min(image.shape[1], x + width + pad)
    y2 = min(image.shape[0], y + height + pad)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    # frame별 vehicle track bbox가 들어오면 이 경로가 곧 multi-frame target crop이 된다.
    scale = 3
    enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return enlarged, (x1, y1), scale


def _to_frame_boxes(boxes, origin, scale):
    """확대 crop OCR box를 원본 프레임 좌표계로 되돌린다."""
    x0, y0 = origin
    return [
        TextBox(
            text=box.text,
            score=box.score,
            box=tuple(round(value / scale) + (x0 if index % 2 == 0 else y0)
                      for index, value in enumerate(box.box)),
        )
        for box in boxes
    ]


class LocalVideoFrameSource:
    """로컬 영상 파일을 직접 연다 — `recording` 연결 전까지 쓰는 경로.

    **`frame_ref`가 임시값이고 `read_frame()`으로 조회되지 않는다.**
    """

    def __init__(self, clip_paths: dict, offsets_sec=SAMPLE_RATIOS):
        """`clip_paths`는 `{incident_clip_ref: 영상 경로}`, `offsets_sec`은 길이 대비 비율.

        2점 이상이어야 하는 이유 — overlay `monotonic_ok`·`duration_match_ok`는 sample 2건
        이상이라야 `null`이 아닌 값이 된다. sample 1건이면 evidence가 이 overlay를 최종
        시각으로 선택하지 않는다(`evidence/time_resolution.py` `_valid_overlay`). 기본값은
        `SAMPLE_RATIOS`.
        """
        if len(offsets_sec) < 2:
            raise ValueError("offsets_sec은 2점 이상이어야 한다 — 1점이면 consensus와 "
                             "overlay 검증이 둘 다 성립하지 않는다")
        self._paths = dict(clip_paths)
        self._offsets = tuple(offsets_sec)

    def frames(self, incident_clip_ref: str) -> list:
        import cv2

        path = self._paths.get(incident_clip_ref)
        if path is None:
            raise ProviderError("INFRA", "READOUT_FRAME_ACCESS_FAILED",
                                f"clip_ref에 대응하는 로컬 영상이 없다: {incident_clip_ref!r}")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ProviderError("INFRA", "READOUT_FRAME_ACCESS_FAILED",
                                f"영상을 열 수 없다: {path}")
        try:
            fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
            duration = (capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0) / fps if fps else 0.0
            out = []
            for ratio in self._offsets:
                at_sec = duration * ratio
                capture.set(cv2.CAP_PROP_POS_MSEC, at_sec * 1000.0)
                ok, image = capture.read()
                if ok:
                    out.append(SourceFrame(
                        # 임시 ref다. 정식 발급은 recording이 한다 — 클래스 docstring.
                        frame_ref=f"fr_provisional_{incident_clip_ref}_{at_sec:07.3f}",
                        offset_sec=round(at_sec, 3),
                        image=image,
                    ))
        finally:
            capture.release()

        if not out:
            raise ProviderError("INFRA", "READOUT_FRAME_ACCESS_FAILED",
                                f"프레임을 한 장도 못 읽었다: {path}")
        return out


def _decode_image(content: bytes):
    """recording이 반환한 PNG bytes를 PaddleOCR 입력 이미지로 바꾼다."""
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ProviderError("INFRA", "READOUT_FRAME_ACCESS_FAILED", "frame PNG를 decode하지 못했습니다")
    return image


class RecordingFrameSource:
    """IncidentClip에서 recording이 발급한 실제 `FrameRef`와 픽셀을 가져온다."""

    def __init__(self, recording, sample_ratios=SAMPLE_RATIOS):
        if len(sample_ratios) < 2 or any(
            not isfinite(ratio) or ratio < 0 or ratio >= 1 for ratio in sample_ratios
        ):
            raise ValueError("sample_ratios는 [0, 1) 범위의 2점 이상이어야 합니다")
        self._recording = recording
        self._ratios = tuple(sample_ratios)

    def frames(self, incident_clip_ref: str) -> list:
        try:
            clip = self._recording.get_incident_clip(incident_clip_ref)
            if clip.duration_sec is None or clip.duration_sec <= 0:
                raise ProviderError(
                    "INFRA", "READOUT_FRAME_ACCESS_FAILED", "incident clip 길이를 알 수 없습니다"
                )
            clip_frames = IncidentClipFrames(self._recording, incident_clip_ref)
            frames = []
            for ratio in self._ratios:
                offset_sec = clip.duration_sec * ratio
                frame, content = clip_frames.read_at(offset_sec)
                frames.append(SourceFrame(
                    frame_ref=frame.frame_ref,
                    offset_sec=round(offset_sec, 3),
                    image=_decode_image(content),
                ))
            return frames
        except ProviderError:
            raise
        except RecordingCapabilityError as error:
            # recording의 상세 오류는 여기서 외부 OCR provider 실패 taxonomy로 접는다.
            raise ProviderError("INFRA", "READOUT_FRAME_ACCESS_FAILED", str(error)) from error


# ── OCR 결과 해석 — 픽셀 없이 검사 가능한 부분 ───────────────

def pick_plate(boxes, *, allow_digits_only=False):
    """프레임 한 장에서 번호판 줄 하나를 고른다. 없으면 `None`.

    형식이 맞는 것을 먼저 보고 그 안에서 신뢰도로 고른다. 형식 후보가 없으면 필터 통과분 중
    신뢰도 최고 — 2줄 아랫줄처럼 형식이 안 맞아도 실제로 읽힌 값인 경우가 있다.
    """
    candidates = [
        b for b in boxes
        if len(re.findall(r"\d", b.text)) >= MIN_DIGITS
        # 납작한 박스를 여기서 버린다. 앞서 `max(height, 1)`로 가리고 있었는데, 그러면
        # 높이 0짜리 박스가 후보로 남아 `best_frame.plate_bbox_xywh`에 [x,y,w,0]으로
        # 실린다 — 계약 §4 최소 유효성의 `h > 0`(invariants R19) 위반이다. provider는
        # 외부 OCR 출력이 들어오는 경계라 여기서 막는다.
        and b.height > 0
        and b.width / b.height >= MIN_ASPECT
        and (HANGUL.search(b.text)
             or (allow_digits_only and DIGITS_ONLY_PLATE.search(b.text)))
        and not TIMESTAMP_PATTERN.search(b.text)
    ]
    if not candidates:
        return None
    formatted = [
        b for b in candidates
        if PLATE_PATTERN.search(b.text)
        or (allow_digits_only and DIGITS_ONLY_PLATE.search(b.text))
    ]
    return max(formatted or candidates, key=lambda b: b.score)


def pick_overlay_line(boxes):
    """날짜가 보이는 줄을 고른다. 여럿이면 신뢰도 최고. **줄을 자르지 않는다.**"""
    dated = [b for b in boxes if TIMESTAMP_PATTERN.search(b.text)]
    return max(dated, key=lambda b: b.score) if dated else None


def association(hint_used: bool, target_hint, *, found: bool) -> AssociationReading:
    """무엇을 대상으로 읽었는지.

    hint가 없을 때 `LOW_CONFIDENCE`를 붙인다 — track1 실측에서 **검출 결과만으로 고르면
    최고 57.7%이고, 틀릴 때 26~33%가 「정상 차량」**이었다(`track1-vehicle-2026-09-19` §2-③).
    조용히 옆 차를 읽는 실패라 `ASSOCIATED`로 내보낼 근거가 없다. 보류를 강제하지는 않는다 —
    `LOW_CONFIDENCE`로 확정을 보류할지는 `evidence`가 정한다(계약 §5).
    """
    if found:
        status = "ASSOCIATED" if hint_used else "LOW_CONFIDENCE"
        evidence = [("SPATIAL_PROXIMITY", "프레임 내 번호판 후보에서 선택")]
    else:
        status = "FAILED" if hint_used else "NOT_PROVIDED"
        evidence = []
    region = None
    bbox = _hint_bbox(target_hint, getattr(target_hint, "frame_ref", None)) if hint_used else None
    if bbox is not None:
        region = (target_hint.frame_ref, list(bbox))
    return AssociationReading(
        status=status,
        target_hint_used=hint_used,
        track_ref=getattr(target_hint, "track_ref", None) if hint_used else None,
        association_method="TARGET_HINT_WITH_FALLBACK" if hint_used else "FALLBACK_ONLY",
        evidence=evidence,
        region=region,
    )


def sharpness(image, box) -> float:
    """번호판 영역의 Laplacian 분산. `_best_index()`가 신뢰도 동점일 때 쓰는 보조 지표다.

    절대 기준이 아니라 **같은 실행 안의 프레임끼리** 비교하는 값이다.
    """
    import cv2

    x1, y1, x2, y2 = box
    crop = image[max(y1, 0):max(y2, 0), max(x1, 0):max(x2, 0)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3)


# ── provider ─────────────────────────────────────────────────

class PaddleOcrProvider(OcrProvider):
    """PaddleOCR 3.7 · PP-OCRv5 korean. 프레임은 `frame_source`가 공급한다."""

    label = "paddleocr-3.7.0-ppocrv5-korean"

    def __init__(self, frame_source, *, tz_offset: str = "+09:00"):
        self._source = frame_source
        self._tz_offset = tz_offset
        """overlay 문자열에는 timezone이 없다. 정식 출처는 clip의 source 메타데이터이고,
        여기 기본값은 **한국 블랙박스 전제의 단순화**다."""
        self._engine = None
        self._frames = {}
        self._seen = {}
        """clip별 프레임과 `(clip_ref, frame_ref)`별 OCR 결과. `read_plate`와
        `read_overlay_time`이 **같은 프레임을 본다** — 없으면 영상을 두 번 열고 OCR을
        두 배로 돌린다."""

    def _clip_frames(self, clip_ref) -> list:
        if clip_ref not in self._frames:
            self._frames[clip_ref] = self._source.frames(clip_ref)
        return self._frames[clip_ref]

    def _boxes(self, clip_ref, frame, target_hint=None) -> list:
        hint_bbox = _hint_bbox(target_hint, frame.frame_ref)
        key = (clip_ref, frame.frame_ref, hint_bbox)
        if key in self._seen:
            return self._seen[key]
        if self._engine is None:
            from paddleocr import PaddleOCR  # 모델 적재가 수 초 걸려 생성자에서 하지 않는다
            self._engine = PaddleOCR(
                lang="korean",
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                enable_mkldnn=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        target_crop = _target_crop(frame.image, target_hint, frame.frame_ref)
        image = target_crop[0] if target_crop else frame.image
        result = next(iter(self._engine.predict(image))).json["res"]
        boxes = [
            TextBox(text=t, score=float(s), box=tuple(int(v) for v in b))
            for t, s, b in zip(result["rec_texts"], result["rec_scores"], result["rec_boxes"])
        ]
        if target_crop:
            boxes = _to_frame_boxes(boxes, target_crop[1], target_crop[2])
        self._seen[key] = boxes
        return boxes

    def read_plate(self, input_ref, target_hint) -> PlateReading:
        clip_ref = input_ref.incident_clip_ref
        frames = self._clip_frames(clip_ref)
        targeted_frames = [
            frame for frame in frames if _hint_bbox(target_hint, frame.frame_ref) is not None
        ]
        # target_hint가 있으면 해당 frame만 읽는다. 불일치한 hint에서 전체 화면을 읽으면
        # 다른 차량 결과를 ASSOCIATED로 잘못 표시할 수 있다.
        frames = targeted_frames if target_hint is not None else frames
        readings = []
        for frame in frames:
            picked = pick_plate(
                self._boxes(clip_ref, frame, target_hint), allow_digits_only=target_hint is not None
            )
            if picked is None:
                continue
            readings.append(PlateFrameReading(
                frame_ref=frame.frame_ref,
                bbox_xywh=[picked.box[0], picked.box[1], picked.width, picked.height],
                text=picked.text,
                confidence=picked.score,
                quality={"plate_px_height": picked.height,
                         "sharpness": sharpness(frame.image, picked.box)},
            ))
        return PlateReading(
            association=association(bool(targeted_frames), target_hint, found=bool(readings)),
            frames=readings,
        )

    def read_overlay_time(self, input_ref) -> OverlayReading:
        clip_ref = input_ref.incident_clip_ref
        samples = []
        for frame in self._clip_frames(clip_ref):
            line = pick_overlay_line(self._boxes(clip_ref, frame))
            if line is not None:
                samples.append(OverlaySampleReading(
                    frame_ref=frame.frame_ref,
                    offset_sec=frame.offset_sec,
                    raw_text=line.text,
                ))
        # 날짜 줄을 못 찾은 것을 「overlay가 없다」로 단정하지 않는다. 우리가 못 본 것과 화면에
        # 없는 것은 다르고, 없다고 하면 사용자가 화면을 다시 보지 않는다(failure-taxonomy.md).
        return OverlayReading(
            presence=PRESENT if samples else UNDETERMINED,
            samples=samples,
            tz_offset=self._tz_offset,
        )


def selfcheck() -> None:
    """픽셀이 필요 없는 판정부만 검사한다. OCR 결과를 손으로 지어내 넣는다."""
    box = lambda t, s, b: TextBox(text=t, score=s, box=b)  # noqa: E731

    # 형식이 맞는 후보를 신뢰도보다 먼저 본다
    assert pick_plate([box("23두4874", 0.80, (100, 100, 300, 160)),
                       box("13가20 0가020", 0.99, (400, 100, 700, 160))]).text == "23두4874"
    # 형식 후보가 없으면 필터 통과분 중 신뢰도 최고 (2줄 번호판 아랫줄)
    assert pick_plate([box("바5215", 0.99, (100, 100, 300, 150))]).text == "바5215"
    # 세로로 긴 것·숫자가 적은 것은 번호판이 아니다
    assert pick_plate([box("12가", 0.99, (0, 0, 200, 90))]) is None
    assert pick_plate([box("가나다라", 0.99, (0, 0, 300, 100))]) is None
    # overlay 줄을 번호판으로 올리지 않는다 — 20260806_061434_EVT_1 실측값이다.
    # 이 영상은 번호판이 검출되지 않아 overlay가 유일한 후보로 남았다.
    assert pick_plate([box("2026/08/06 06:14:34 13.80 X:+0.062 Y:*0.020 2:-0.062",
                           0.95, (300, 1000, 1200, 1040))]) is None
    # 한글이 없는 오인식도 후보가 아니다 (baseline 백색 1줄의 한글 누락 프레임)
    assert pick_plate([box("2354874", 0.91, (100, 100, 300, 160))]) is None
    # 대상 차량 crop 안에서는 한글이 빠진 1줄 판독을 보존한다. 전체 화면에서는 overlay
    # 오탐 방지를 위해 여전히 버린다.
    digits_only = box("36 3105", 0.93, (100, 100, 300, 160))
    assert pick_plate([digits_only]) is None
    assert pick_plate([digits_only], allow_digits_only=True).text == "36 3105"
    # target crop OCR 좌표는 원본 frame 좌표로 되돌아간다
    restored = _to_frame_boxes([box("23두4874", 0.99, (30, 60, 330, 120))], (10, 20), 3)[0]
    assert restored.box == (20, 40, 120, 60)
    # 높이 0짜리 박스는 후보가 아니다 — 통과시키면 plate_bbox_xywh가 [x,y,w,0]으로
    # 나가 R19의 h > 0을 어긴다
    assert pick_plate([box("23두4874", 0.99, (100, 100, 300, 100))]) is None

    # overlay 줄은 자르지 않고 통째로 넘긴다 — 시각 추출은 api.py가 한다
    raw = "2026/08/10 17:57:36 13.20 ×:+0.020 Y:-0.043 2:-0.012"
    assert pick_overlay_line([box(raw, 0.97, (0, 1000, 800, 1040))]).text == raw
    assert pick_overlay_line([box("17:57:36", 0.99, (0, 0, 10, 10))]) is None

    # hint 없이 찾았으면 LOW_CONFIDENCE — 조용한 오답을 ASSOCIATED로 내보내지 않는다
    assert association(False, None, found=True).status == "LOW_CONFIDENCE"
    assert association(True, None, found=True).status == "ASSOCIATED"
    assert association(False, None, found=False).status == "NOT_PROVIDED"
    assert association(True, None, found=False).status == "FAILED"

    # 1점짜리 frame source는 만들 수 없다 — consensus·overlay 검증이 성립하지 않는다
    try:
        LocalVideoFrameSource({}, offsets_sec=(0.5,))
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("1점 offsets_sec이 통과했다")

    print("selfcheck ok")


if __name__ == "__main__":
    selfcheck()
