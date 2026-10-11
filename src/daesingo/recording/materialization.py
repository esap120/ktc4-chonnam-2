"""실행별 profile configuration과 로컬 VIDEO materialization. Canonical profile 목록이 아니다."""

from dataclasses import dataclass
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .errors import RecordingCapabilityError
from .models import AssetSpan, TimeRange
from .probe import LocalSource, _snapshot
from .observability import observed_materialization, phase
from .inspection import active_inspections
from .analysis_tail import TailDecodeFailure, allowed, report, validate_tail


class _FrameCoverageError(RecordingCapabilityError):
    """정적인 진단문만 사용하여 공통 엔진의 coverage 실패 원인을 보존한다."""

    def __init__(self, message):
        super().__init__("UNSUPPORTED_MEDIA", message)


@dataclass(frozen=True)
class AnalysisProfile:
    height: int
    preset: str
    crf: int

    def __post_init__(self):
        if type(self.height) is not int or self.height <= 0 or self.height % 2:
            raise ValueError("height는 양의 짝수여야 합니다")
        if self.preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"}:
            raise ValueError("지원하지 않는 encoder preset입니다")
        if type(self.crf) is not int or not 0 <= self.crf <= 51:
            raise ValueError("crf는 0부터 51 사이 정수여야 합니다")


@dataclass(frozen=True)
class MaterializedVideo:
    content: bytes
    duration_sec: float
    timeline_range: TimeRange
    # 내부 연결 검증용 관측값. Canonical AnalysisSource에는 직렬화하지 않는다.
    frames: tuple[tuple[Fraction, Fraction], ...] = ()
    time_base: Fraction | None = None
    video_size: tuple[int, int] | None = None
    best_effort: bool = False


def _millisecond_quantization(payload, base, frames):
    """좁은 Matroska 반올림 패턴만 인정한다. fps를 생성/길이 추정에 사용하지 않는다."""
    if (base != Fraction(1, 1000)
            or "matroska" not in payload.get("format", {}).get("format_name", "").split(",")
            or len(frames) < 3 or len({length for _, length in frames}) != 1):
        return False
    length = frames[0][1]
    if length <= base:
        return False
    # 모든 PTS가 동일 주기를 nearest-tick으로 반올림한 시각과 양립해야 한다.
    # 각 frame의 제약을 교차시켜 단발 gap이나 누적 drift를 무조건 허용하지 않는다.
    lower, upper = length - base, length + base
    origin = frames[0][0]
    for i, (at, _) in enumerate(frames[1:], 1):
        lower = max(lower, (at - origin - base / 2) / i)
        upper = min(upper, (at - origin + base / 2) / i)
    return lower < upper


class LocalAnalysisMaterializer:
    def __init__(self, profiles: dict[str, AnalysisProfile], *, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 timeout_sec=120.0, temp_root: Path | None = None):
        if not math.isfinite(timeout_sec) or timeout_sec <= 0:
            raise ValueError("유한한 양수 timeout이 필요합니다")
        if any(not isinstance(k, str) or not k or not isinstance(v, AnalysisProfile) for k, v in profiles.items()):
            raise ValueError("opaque ref와 명시적인 profile configuration이 필요합니다")
        self._profiles = dict(profiles)
        self._ffmpeg, self._ffprobe = ffmpeg, ffprobe
        self._timeout = timeout_sec
        self._temp_root = temp_root

    def has_profile(self, ref):
        return ref in self._profiles

    def _run(self, args):
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=self._timeout, check=False)
        if result.returncode:
            if ("-vf" in args and "-xerror" in args
                    and b"No start code is found" in result.stderr
                    and b"Error submitting packet to decoder" in result.stderr):
                raise TailDecodeFailure()
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "media 도구가 작업을 완료하지 못했습니다")
        return result.stdout

    def _probe(self, path, index=None):
        args = [self._ffprobe, "-v", "error", "-protocol_whitelist", "file"]
        if index is not None:
            args += ["-select_streams", str(index)]
        args += ["-show_frames", "-show_entries",
                 "format=format_name,duration:stream=codec_type,codec_name,width,height,pix_fmt,time_base,duration:frame=best_effort_timestamp,duration,pkt_duration",
                 "-of", "json", str(path)]
        return json.loads(self._run(args))

    def _verify_tail(self, source, index, base, frames, audit):
        # ordinal은 등록된 stream 목록의 실제 index로 검사한다. 역할을 추론하지 않는다.
        videos = [s.index for s in source.streams if s.media_type == "VIDEO"]
        if not videos or index != videos[0]:
            raise ValueError("명시적 VIDEO ordinal 0만 허용합니다")
        with source.path.open("rb") as file:
            header = file.read(12)
        if header[:4] != b"RIFF" or header[8:] != b"AVI ":
            raise ValueError("AVI 후행 패턴만 지원합니다")
        payload = json.loads(self._run([self._ffprobe, "-v", "error", "-protocol_whitelist", "file",
            "-select_streams", str(index), "-show_frames", "-show_packets", "-show_entries",
            "format=format_name:stream=codec_name,has_b_frames:frame=best_effort_timestamp,pkt_pos,pkt_size,decode_error_flags:packet=pos,size,pts,dts",
            "-of", "json", str(source.path)]))
        # 기존 inspection과 독립 조회가 모두 같은 PTS를 관측해야 한다.
        ticks = [at / base for at, _ in frames]
        if any(t.denominator != 1 for t in ticks):
            raise ValueError("frame PTS 근거 부족")
        return validate_tail(payload, int.from_bytes(header[4:8], "little") + 8,
                             source.byte_size, [int(t) for t in ticks], audit=audit)

    def _strict_decode(self, path):
        self._run([self._ffmpeg, "-nostdin", "-v", "error", "-xerror",
            "-protocol_whitelist", "file", "-i", str(path), "-map", "0:v:0",
            "-an", "-sn", "-dn", "-f", "null", "-"])

    @staticmethod
    def _frames(payload, *, expected_coverage=None):
        streams = payload["streams"]
        if len(streams) != 1 or streams[0]["codec_type"] != "video":
            raise ValueError("단일 VIDEO 검증 실패")
        base = Fraction(streams[0]["time_base"])
        if base <= 0:
            raise ValueError("유효하지 않은 time base")
        raw_frames = payload["frames"]
        timestamps = [int(f["best_effort_timestamp"]) * base for f in raw_frames]
        if not timestamps or any(b <= a for a, b in zip(timestamps, timestamps[1:])):
            raise _FrameCoverageError("frame timestamp가 없거나 엄격히 증가하지 않습니다")
        frames = []
        for i, (frame, at) in enumerate(zip(raw_frames, timestamps)):
            # 구버전 ffprobe는 duration 대신 pkt_duration을 제공한다. 단위는 stream time_base다.
            observed = [int(frame[key]) * base for key in ("duration", "pkt_duration")
                        if frame.get(key) not in (None, "N/A")]
            if any(length <= 0 for length in observed) or len(set(observed)) > 1:
                raise _FrameCoverageError("frame duration 관찰값이 유효하지 않거나 서로 다릅니다")
            if observed:
                length = observed[0]
            elif i + 1 < len(timestamps):
                # 다음 presentation timestamp까지의 표시 구간. 일정 fps를 가정하지 않는다.
                length = timestamps[i + 1] - at
            else:
                # 검증한 원본 coverage와 출력의 모든 상대 PTS/개수, stream 끝을
                # 교차 확인한다. container 길이나 고정 fps만으로 tail을 추정하지 않는다.
                matched = (expected_coverage is not None
                    and len(timestamps) == len(expected_coverage)
                    and timestamps[0] == 0
                    and all(at == expected_at and length > 0
                            for at, (expected_at, length) in zip(timestamps, expected_coverage))
                    and all(a + length == b for (a, length), (b, _) in
                            zip(expected_coverage, expected_coverage[1:])))
                try:
                    stream_end = Fraction(streams[0].get("duration", "N/A"))
                except (ValueError, TypeError, ZeroDivisionError):
                    stream_end = None
                if (not matched or stream_end != expected_coverage[-1][0] + expected_coverage[-1][1]):
                    raise _FrameCoverageError("마지막 frame duration 근거가 없습니다 (duration/pkt_duration 누락)")
                length = stream_end - at
            frames.append((at, length))
        if any(a + length != b for (a, length), (b, _) in zip(frames, frames[1:])):
            # 출력은 검증된 millisecond source에서 선택한 PTS와 정확히 같을 때만 허용한다.
            matched_output = (expected_coverage is not None and base == Fraction(1, 1000)
                and len(frames) == len(expected_coverage)
                and all(at - frames[0][0] == expected_at
                        for (at, _), (expected_at, _) in zip(frames, expected_coverage)))
            if ((not matched_output and not _millisecond_quantization(payload, base, frames))
                    or any(abs(b - a - length) > base
                           for (a, length), (b, _) in zip(frames, frames[1:]))):
                raise _FrameCoverageError("불연속 frame coverage는 지원하지 않습니다")
            # PTS는 보존한다. 중간 coverage만 다음 관측 PTS까지 정규화한다.
            # 마지막 frame은 위에서 검증한 duration/출력 coverage 근거를 그대로 유지한다.
            frames = [(a, b - a) for (a, _), (b, _) in zip(frames, frames[1:])] + [frames[-1]]
        return base, [(at - frames[0][0], length) for at, length in frames]

    @observed_materialization
    def materialize(self, source: LocalSource, index: int, span: AssetSpan, profile_ref: str) -> MaterializedVideo:
        if profile_ref not in self._profiles:
            raise ValueError("등록되지 않은 profile_ref입니다")
        profile = self._profiles[profile_ref]
        inspections = active_inspections()
        inspection_key = None
        completed = False
        fallback = False
        audit = None
        try:
            with phase("source_snapshot"):
                before = _snapshot(source.path)
                if (before[2], before[3], before[4]) != (source.byte_size, source.mtime_ns, source.sha256):
                    raise RecordingCapabilityError("UNAVAILABLE", "등록 이후 원본이 변경되었습니다")
            with phase("source_probe"):
                # snapshot에는 device/inode/크기/mtime/SHA-256이 포함된다.
                # 서로 다른 probe 실행 설정은 보수적으로 공유하지 않는다.
                inspection_key = (before, index, self._ffprobe)
                inspected = inspections.get(inspection_key) if inspections is not None else None
                if inspected is None:
                    raw = self._probe(source.path, index)
                    base, frames = self._frames(raw)
                    # raw frame JSON은 보관하지 않고 검증된 coverage와 stream metadata만 보관한다.
                    inspected = ({"streams": raw["streams"], "format": raw.get("format", {})}, base, frames)
                raw, base, frames = inspected
            with phase("frame_prepare"):
                input_stream = raw["streams"][0]
                width = max(2, 2 * math.floor(input_stream["width"] * profile.height / input_stream["height"] / 2 + 0.5))
                start, end = Fraction(str(span.source_range.start_sec)), Fraction(str(span.source_range.end_sec))
                selected = [(i, at, length) for i, (at, length) in enumerate(frames) if start <= at < end]
                if not selected:
                    raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "요청 구간에 선택 가능한 frame이 없습니다")
                first, last = selected[0], selected[-1]
                # 출력은 frame 경계의 실제 coverage를 보존한다. 요청 시각으로 위장하지 않는다.
                actual_start, actual_end = first[1], last[1] + last[2]
            with TemporaryDirectory(prefix="recording-analysis-", dir=self._temp_root) as work:
                output = Path(work) / "prepared.mp4"
                with phase("encode"):
                    command = [self._ffmpeg, "-nostdin", "-v", "error", "-xerror", "-n",
                        "-protocol_whitelist", "file", "-noautorotate", "-i", str(source.path),
                        "-map", f"0:{index}", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
                        "-vf", f"trim=start_frame={first[0]}:end_frame={last[0]+1},setpts=PTS-STARTPTS,scale={width}:{profile.height}",
                        "-fps_mode", "passthrough", "-enc_time_base", str(base),
                        "-video_track_timescale", str(base.denominator),
                        "-c:v", "libx264", "-preset", profile.preset, "-crf", str(profile.crf),
                        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
                    try:
                        self._run(command)
                    except TailDecodeFailure:
                        if not allowed():
                            raise
                        audit = dict(best_effort=False, strict_failure_stage="encode",
                            decode_error_flags_observed=False,
                            tail_verified=False, coverage_verified=False, output_verified=None,
                            output_strict_decode=None, source_unchanged=None, cleanup=False)
                        if any(a + length != b for (a, length), (b, _) in zip(frames, frames[1:])):
                            raise ValueError("연속 coverage가 필요합니다")
                        audit["coverage_verified"] = True
                        audit["tail_packets"] = self._verify_tail(source, index, base, frames, audit)
                        audit["tail_verified"] = True
                        if _snapshot(source.path) != before:
                            raise RecordingCapabilityError("UNAVAILABLE", "변환 중 원본 변경을 감지했습니다")
                        # 실패한 파생 파일만 제거한다. 원본 packet/시각은 수정하지 않는다.
                        output.unlink(missing_ok=True)
                        self._run([arg for arg in command if arg != "-xerror"])
                        fallback = True
                with phase("output_probe"):
                    probed = self._probe(output)
                with phase("output_validate"):
                    if audit is not None:
                        audit["output_verified"] = False
                    expected = ([(at - actual_start, length) for _, at, length in selected]
                        if fallback or (base == Fraction(1, 1000)
                        and "matroska" in raw.get("format", {}).get("format_name", "").split(",")) else None)
                    output_base, output_frames = self._frames(probed, expected_coverage=expected)
                    stream = probed["streams"][0]
                    if (stream["codec_name"] != "h264" or stream["height"] != profile.height
                            or stream["width"] != width or stream["pix_fmt"] != "yuv420p"
                            or "mp4" not in probed["format"]["format_name"].split(",")
                            or len(output_frames) != len(selected)):
                        raise ValueError("출력 media 형식 불일치")
                    tolerance = 0 if fallback else 2 * output_base
                    for (_, at, length), (out_at, out_length) in zip(selected, output_frames):
                        if abs(at - actual_start - out_at) > tolerance or abs(length - out_length) > tolerance:
                            raise ValueError("출력 frame timestamp 불일치")
                    duration = float(probed["format"]["duration"])
                    # MP4 format duration은 millisecond 단위로 반올림될 수 있다.
                    if (not math.isfinite(duration) or duration <= 0
                            or abs(duration - float(actual_end - actual_start)) > 0.001 + float(tolerance)):
                        raise ValueError("출력 duration 불일치")
                if fallback:
                    audit["output_verified"] = True
                    audit["output_strict_decode"] = False
                    self._strict_decode(output)
                    audit["output_strict_decode"] = True
                with phase("bytes_read"):
                    content = output.read_bytes()
                with phase("bytes_validate"):
                    if not content:
                        raise ValueError("빈 출력 media")
                    boxes, position = [], 0
                    while position + 8 <= len(content):
                        size = int.from_bytes(content[position:position+4], "big")
                        boxes.append(content[position+4:position+8])
                        if size < 8:
                            raise ValueError("지원하지 않는 MP4 box")
                        position += size
                    if position != len(content) or boxes.index(b"moov") > boxes.index(b"mdat"):
                        raise ValueError("faststart 검증 실패")
                with phase("source_verify"):
                    if _snapshot(source.path) != before:
                        raise RecordingCapabilityError("UNAVAILABLE", "변환 중 원본 변경을 감지했습니다")
                if audit is not None:
                    audit["source_unchanged"] = True
                shift = Fraction(str(span.timeline_range.start_sec)) - start
                result = MaterializedVideo(content, duration, TimeRange(
                    start_sec=float(shift + actual_start), end_sec=float(shift + actual_end)),
                    tuple(output_frames), output_base, (width, profile.height), fallback)
            # 출력 검증·원본 재검사·cleanup까지 성공한 inspection만 공유한다.
            if inspections is not None:
                inspections.put(inspection_key, inspected)
            completed = True
            return result
        except subprocess.TimeoutExpired:
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "materialization 제한 시간을 초과했습니다") from None
        except OSError:
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "media 파일 또는 도구에 접근할 수 없습니다") from None
        except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError):
            raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "실제 media의 형식·frame coverage·시각을 검증할 수 없습니다") from None
        finally:
            if audit is not None:
                audit["cleanup"] = not output.parent.exists()
                # 실패 경로에서도 변경/소실을 검사하며 원본/예외 원문은 기록하지 않는다.
                if not completed:
                    try:
                        audit["source_unchanged"] = _snapshot(source.path) == before
                    except (OSError, ValueError, RecordingCapabilityError):
                        audit["source_unchanged"] = False
                audit["best_effort"] = completed and fallback
                report(audit)
            if inspections is not None and inspection_key is not None and not completed:
                inspections.discard(inspection_key)
