"""#252: Search 실행 범위의 좁은 AVI 후행 packet 예외. 공개 계약이 아니다."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging

from .errors import RecordingCapabilityError

_allowed = ContextVar("search_analysis_tail", default=False)
logger = logging.getLogger(__name__)


@contextmanager
def analysis_tail_scope(enabled=True):
    token = _allowed.set(enabled)
    try:
        yield
    finally:
        _allowed.reset(token)


def allowed():
    return _allowed.get()


class TailDecodeFailure(RecordingCapabilityError):
    """stderr는 보관하지 않는다. 공개 failure code는 기존 값을 유지한다."""
    def __init__(self):
        super().__init__("TEMPORARY_FAILURE", "media 도구가 작업을 완료하지 못했습니다")


def report(checks):
    # 호출부는 정적인 key와 bool/정수만 전달한다. 경로/예외/명령은 받지 않는다.
    logger.info("analysis_tail %s", json.dumps(checks, sort_keys=True))


def validate_tail(payload, riff_end, file_size, expected_pts, *, audit=None):
    """frame/packet의 일대일 대응 및 관측된 16-byte 후행 패턴만 인정한다.

    decode_error_flags 부재를 0으로 주장하지 않는다. #252의 후보 위치 정책이며
    B-frame, 누락된 위치, RIFF 내부 오류 및 오류 뒤 decoded frame은 거부한다.
    """
    try:
        stream, = payload["streams"]
        if (stream["codec_name"] != "h264" or stream["has_b_frames"] != 0
                or payload["format"]["format_name"] != "avi"):
            raise ValueError
        rows = payload["packets_and_frames"]
        frames = [x for x in rows if x["type"] == "frame"]
        packets = [x for x in rows if x["type"] == "packet"]
        if audit is not None:
            # 모든 decoded frame에서 관측됐을 때만 true. 일부 누락도 false다.
            audit["decode_error_flags_observed"] = bool(frames) and all(
                "decode_error_flags" in f for f in frames)
        positions = [int(f["pkt_pos"]) for f in frames]
        packet_positions = [int(p["pos"]) for p in packets]
        packet_ends = [int(p["pos"]) + int(p["size"]) for p in packets]
        if (not frames or len(set(positions)) != len(positions)
                or len(set(packet_positions)) != len(packet_positions)
                or any(b <= a for a, b in zip(positions, positions[1:]))
                or any(b <= a for a, b in zip(packet_positions, packet_positions[1:]))
                or any(end <= start for start, end in zip(packet_positions, packet_ends))
                or any(end > start for end, start in zip(packet_ends, packet_positions[1:]))
                or [int(f["best_effort_timestamp"]) for f in frames] != expected_pts
                or any("decode_error_flags" in f and int(f["decode_error_flags"]) != 0 for f in frames)):
            raise ValueError
        by_pos = {int(p["pos"]): p for p in packets}
        for f, pos in zip(frames, positions):
            p = by_pos[pos]
            if (int(p["size"]) != int(f["pkt_size"])
                    # AVI는 PTS 없이 DTS만 제공할 수 있다. 위에서 B-frame=0을
                    # 확인한 경우에만 실제 DTS와 frame PTS의 일치를 검사한다.
                    or int(p.get("pts", p.get("dts"))) != int(f["best_effort_timestamp"])):
                raise ValueError
        tail = [p for p in packets if int(p["pos"]) not in set(positions)]
        last_frame_packet_end = positions[-1] + int(by_pos[positions[-1]]["size"])
        if (not tail or not 12 < riff_end < file_size
                or any(int(p["size"]) != 16 or int(p["pos"]) < last_frame_packet_end
                       or int(p["pos"]) < riff_end for p in tail)
                or any(int(p["pos"]) < 0 or int(p["pos"]) + int(p["size"]) > file_size for p in packets)):
            raise ValueError
        return len(tail)
    except (KeyError, TypeError, OverflowError):
        raise ValueError("후행 packet 근거 부족") from None
