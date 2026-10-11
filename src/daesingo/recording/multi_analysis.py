"""검증된 단일 구간 출력을 연결한다. 경계 gap/overlap을 보정하지 않는다."""
from fractions import Fraction
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .errors import RecordingCapabilityError
from .materialization import MaterializedVideo
from .models import TimeRange
from .probe import _snapshot


def materialize_chain(engine, inputs, profile_ref):
    try:
        snapshots = [_snapshot(source.path) for source, _, _ in inputs]
        for (source, _, _), snapshot in zip(inputs, snapshots):
            if snapshot[2:] != (source.byte_size, source.mtime_ns, source.sha256):
                raise RecordingCapabilityError("UNAVAILABLE", "등록 이후 원본이 변경되었습니다")
        parts = [engine.materialize(source, index, span, profile_ref) for source, index, span in inputs]
        best_effort = any(p.best_effort for p in parts)
        if any(not p.frames or p.time_base != parts[0].time_base or p.video_size != parts[0].video_size for p in parts):
            raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "연결할 출력의 time base 또는 해상도가 일치하지 않습니다")
        # 초 단위 decimal metadata의 표현 오차에만 사용하는 비교 상한이다.
        # 한 tick/frame보다 항상 작게 제한하며 timestamp/range는 수정하지 않는다.
        tolerance = min(Fraction(1, 1000000), parts[0].time_base / 2,
                        min(length for p in parts for _, length in p.frames) / 2)
        if tolerance <= 0:
            raise ValueError("유효하지 않은 frame 정밀도")
        if any(abs(Fraction(str(a.timeline_range.end_sec)) - Fraction(str(b.timeline_range.start_sec))) > tolerance
               for a, b in zip(parts, parts[1:])):
            raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "실제 frame 경계가 연속되지 않습니다")
        expected, offset = [], Fraction(0)
        for p in parts:
            expected.extend((offset + at, length) for at, length in p.frames)
            offset += p.frames[-1][0] + p.frames[-1][1]
        timeline_range = TimeRange(start_sec=parts[0].timeline_range.start_sec, end_sec=parts[-1].timeline_range.end_sec)
        # 여러 seam의 오차가 누적돼도 전체 허용 폭을 늘리지 않는다.
        timeline_length = Fraction(str(timeline_range.end_sec)) - Fraction(str(timeline_range.start_sec))
        if abs(offset - timeline_length) > tolerance:
            raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "연결 coverage와 Timeline 길이가 일치하지 않습니다")
        with TemporaryDirectory(prefix="recording-chain-", dir=engine._temp_root) as work:
            root = Path(work)
            lines = ["ffconcat version 1.0"]
            for i, p in enumerate(parts):
                name = f"part-{i}.mp4"
                (root / name).write_bytes(p.content)
                lines.extend([f"file {name}", f"duration {float(p.frames[-1][0] + p.frames[-1][1]):.12f}"])
            manifest = root / "parts.txt"
            manifest.write_text("\n".join(lines) + "\n", encoding="ascii")
            output = root / "prepared.mp4"
            engine._run([engine._ffmpeg, "-nostdin", "-v", "error", "-xerror", "-n",
                "-protocol_whitelist", "file", "-f", "concat", "-safe", "1", "-i", str(manifest),
                "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
                "-c:v", "copy", "-video_track_timescale", str(parts[0].time_base.denominator),
                "-movflags", "+faststart", str(output)])
            raw = engine._probe(output)
            base, frames = engine._frames(raw, expected_coverage=expected)
            stream = raw["streams"][0]
            if (stream["codec_name"] != "h264" or stream["pix_fmt"] != "yuv420p"
                    or (stream["width"], stream["height"]) != parts[0].video_size
                    or "mp4" not in raw["format"]["format_name"].split(",")
                    or len(frames) != len(expected)
                    or any(abs(a - b) > (0 if best_effort else 2 * base)
                           or abs(x - y) > (0 if best_effort else 2 * base)
                           for (a, x), (b, y) in zip(frames, expected))):
                raise ValueError("연결 출력 검증 실패")
            duration = float(raw["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0 or abs(duration - float(offset)) > .001 + float(2 * base):
                raise ValueError("연결 출력 duration 불일치")
            engine._strict_decode(output)
            content = output.read_bytes()
            boxes, position = [], 0
            while position + 8 <= len(content):
                size = int.from_bytes(content[position:position+4], "big")
                boxes.append(content[position+4:position+8])
                if size < 8:
                    raise ValueError("MP4 box 검증 실패")
                position += size
            if position != len(content) or boxes.index(b"moov") > boxes.index(b"mdat"):
                raise ValueError("faststart 검증 실패")
            if any(_snapshot(source.path) != before for (source, _, _), before in zip(inputs, snapshots)):
                raise RecordingCapabilityError("UNAVAILABLE", "연결 중 원본 변경을 감지했습니다")
            return MaterializedVideo(content, duration, timeline_range, tuple(frames), base, parts[0].video_size, best_effort)
    except subprocess.TimeoutExpired:
        raise RecordingCapabilityError("TEMPORARY_FAILURE", "연결 materialization 제한 시간을 초과했습니다") from None
    except OSError:
        raise RecordingCapabilityError("TEMPORARY_FAILURE", "media 파일 또는 도구에 접근할 수 없습니다") from None
    except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError):
        raise RecordingCapabilityError("UNSUPPORTED_MEDIA", "연결 출력의 형식·frame coverage를 검증할 수 없습니다") from None
