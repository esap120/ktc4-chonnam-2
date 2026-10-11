"""공개 capability의 다중 원본 prepared media 검증."""
import json
import os
from pathlib import Path
import subprocess
from dataclasses import replace
from fractions import Fraction

import pytest

from daesingo.recording import AnalysisProfile, LocalAnalysisMaterializer, RecordingCapabilityError, RecordingService
from tests.recording.test_local_analysis_source import fingerprint


@pytest.fixture
def chain(tmp_path):
    paths = []
    for i, color in enumerate(("red", "blue", "green")):
        path = tmp_path / f"source-{i}.avi"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "lavfi", "-i",
            f"color=c={color}:s=64x48:r=10:d=2", "-c:v", "mpeg4", str(path)],
            check=True, capture_output=True, timeout=30)
        paths.append(path)
    work = tmp_path / "work"
    work.mkdir()
    engine = LocalAnalysisMaterializer({"profile": AnalysisProfile(48, "veryfast", 23)}, temp_root=work)
    with RecordingService(analysis_materializer=engine) as service:
        registered = [service.register_local_source(p) for p in paths]
        rows = [dict(source_asset_ref=r.source_asset.source_asset_ref,
            media_stream_ref=r.media_streams[0].media_stream_ref,
            timeline_start_sec=float(2*i), timeline_end_sec=float(2*i+2))
            for i, r in enumerate(registered)]
        timeline = service.create_relative_timeline_from_placements(rows)
        resolution = service.resolve_span(dict(timeline_id=timeline.timeline_id, revision=timeline.revision),
            dict(start_sec=1., end_sec=5.), media_stream_refs=[r["media_stream_ref"] for r in rows])
        yield service, resolution, paths, work, engine


def test_three_sources_order_bytes_provenance_and_cleanup(chain, tmp_path):
    service, resolution, paths, work, _ = chain
    before = [fingerprint(p) for p in paths]
    source = service.prepare_analysis_source_from_resolution(resolution, "profile")
    shuffled = resolution.model_dump()
    shuffled["spans"] = shuffled["spans"][::-1]
    assert service.prepare_analysis_source_from_resolution(shuffled, "profile") == source
    assert source.duration_sec == 4.
    assert source.timeline_range == resolution.requested_range
    assert source.timeline_ref == resolution.timeline_ref
    assert [r.ref for r in source.source_refs] == [s.source_asset_ref for s in resolution.spans]
    assert source.media_stream_refs == [s.media_stream_ref for s in resolution.spans]
    with service.open_analysis_source(source.analysis_source_ref).stream as stream:
        content = stream.read()
    with service.open_analysis_source(source.analysis_source_ref).stream as stream:
        assert stream.read() == content
    assert len(content) == source.byte_size > 0
    target = tmp_path / "output.mp4"
    target.write_bytes(content)
    raw = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)],
        capture_output=True, check=True, timeout=30)
    data = json.loads(raw.stdout)
    assert len(data["streams"]) == 1 and int(data["streams"][0]["nb_frames"]) == 40
    assert float(data["format"]["duration"]) == source.duration_sec
    pixels = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(target),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=True, timeout=30).stdout
    frames = [pixels[i:i+64*48*3] for i in range(0, len(pixels), 64*48*3)]
    assert len(frames) == 40
    for i, frame in enumerate(frames):
        r, g, b = frame[:3]
        assert (r > 230 and b < 10) if i < 10 else ((b > 230 and r < 10) if i < 30 else (g > 110 and r < 10))
    assert [fingerprint(p) for p in paths] == before
    assert not list(work.iterdir())
    assert all(str(p) not in source.model_dump_json() and p.name not in source.model_dump_json() for p in paths)


@pytest.mark.parametrize("bad", ["sequence", "duplicate", "offset", "gap", "missing", "changed", "encode"])
def test_invalid_or_failed_multi_span_never_published(chain, monkeypatch, bad):
    service, resolution, paths, work, engine = chain
    data = resolution.model_dump()
    expected = ValueError
    if bad == "sequence": data["spans"][0]["sequence"], data["spans"][1]["sequence"] = 1, 0
    elif bad == "duplicate": data["spans"][1] = data["spans"][0].copy()
    elif bad == "offset": data["spans"][1]["source_range"]["start_sec"] = .1
    elif bad == "gap": data["spans"][1]["timeline_range"]["start_sec"] += .1
    elif bad == "missing": paths[1].unlink(); expected = RecordingCapabilityError
    elif bad == "changed": paths[1].write_bytes(b"changed synthetic input"); expected = RecordingCapabilityError
    elif bad == "encode":
        def fail(args):
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "media 도구 실행 실패")
        monkeypatch.setattr(engine, "_run", fail)
        expected = RecordingCapabilityError
    with pytest.raises(expected):
        service.prepare_analysis_source_from_resolution(data, "profile")
    assert not service._local_analysis and not list(work.iterdir())


@pytest.mark.parametrize("status", ["PARTIAL", "FAILED"])
def test_gap_resolution_rejected(chain, status):
    service, resolution, _, work, _ = chain
    data = resolution.model_dump()
    data["status"] = status
    if status == "PARTIAL":
        data["spans"][-1]["timeline_range"]["end_sec"] = 4.5
        data["spans"][-1]["source_range"]["end_sec"] = .5
        data["missing_ranges"] = [dict(timeline_range=dict(start_sec=4.5, end_sec=5.), reason="TIMELINE_GAP", source_ref=None)]
    else:
        data["spans"] = []
        data["failure"] = dict(kind="UNAVAILABLE", code="NO_USABLE_SPAN")
    with pytest.raises(RecordingCapabilityError) as caught:
        service.prepare_analysis_source_from_resolution(data, "profile")
    assert caught.value.code == ("TIMELINE_GAP" if status == "PARTIAL" else "NO_USABLE_SPAN")
    assert not service._local_analysis and not list(work.iterdir())


@pytest.mark.parametrize("mode", ["concat", "timeout", "mutation", "coverage", "output"])
def test_failure_after_parts_cleanup_and_safe_error(chain, monkeypatch, mode):
    service, resolution, paths, work, engine = chain
    original_run = engine._run
    original_materialize = engine.materialize
    original_probe = engine._probe

    def run(args):
        if "concat" in args:
            if mode == "concat":
                raise RecordingCapabilityError("TEMPORARY_FAILURE", "연결 도구 실패")
            if mode == "timeout":
                raise subprocess.TimeoutExpired(args, 1, stderr=b"private stderr")
            if mode == "mutation":
                paths[0].write_bytes(b"synthetic mutation after encode")
        return original_run(args)

    def materialize(*args):
        result = original_materialize(*args)
        if mode == "coverage" and args[2].sequence == 0:
            result.timeline_range.end_sec -= .1
        return result

    def probe(path, index=None):
        result = original_probe(path, index)
        if mode == "output" and path.parent.name.startswith("recording-chain-"):
            result["frames"].pop()
        return result

    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "materialize", materialize)
    monkeypatch.setattr(engine, "_probe", probe)
    with pytest.raises(RecordingCapabilityError) as caught:
        service.prepare_analysis_source_from_resolution(resolution, "profile")
    assert caught.value.code == {"concat": "TEMPORARY_FAILURE", "timeout": "TEMPORARY_FAILURE",
        "mutation": "UNAVAILABLE", "coverage": "UNSUPPORTED_MEDIA", "output": "UNSUPPORTED_MEDIA"}[mode]
    assert all(str(p) not in str(caught.value) and p.name not in str(caught.value) for p in paths)
    assert "private stderr" not in str(caught.value)
    assert not service._local_analysis and not list(work.iterdir())


def test_two_spans_within_larger_timeline_and_actual_outer_range(chain):
    service, original, paths, work, _ = chain
    before = [fingerprint(p) for p in paths]
    resolution = service.resolve_span(original.timeline_ref, dict(start_sec=1.05, end_sec=2.26),
        media_stream_refs=[s.media_stream_ref for s in original.spans])
    assert len(resolution.spans) == 2
    result = service.prepare_analysis_source_from_resolution(resolution, "profile")
    assert result.timeline_range.start_sec == 1.1 and result.timeline_range.end_sec == 2.3
    assert result.duration_sec == 1.2
    assert [r.ref for r in result.source_refs] == [s.source_asset_ref for s in resolution.spans]
    assert [fingerprint(p) for p in paths] == before and not list(work.iterdir())
    paths[0].write_bytes(b"synthetic changed after cache")
    with pytest.raises(RecordingCapabilityError):
        service.prepare_analysis_source_from_resolution(resolution, "profile")


def test_opt_in_tail_only_real_pair_analysis(tmp_path, monkeypatch):
    paths = [os.environ.get("DAESINGO_RECORDING_PAIR_A"), os.environ.get("DAESINGO_RECORDING_PAIR_B")]
    placement_json = os.environ.get("DAESINGO_RECORDING_CHAIN_PLACEMENTS")
    if not all(paths) or not placement_json:
        pytest.skip("실제 pair와 명시적 실험 placement opt-in 필요")
    paths = [Path(p) for p in paths]
    bounds = json.loads(placement_json)
    before = [fingerprint(p) for p in paths]
    work = tmp_path / "work"
    work.mkdir()
    engine = LocalAnalysisMaterializer({"profile": AnalysisProfile(480, "veryfast", 23)}, temp_root=work)
    attempted = []
    original = engine.materialize

    def track(*args):
        attempted.append(args[2].sequence)
        return original(*args)

    monkeypatch.setattr(engine, "materialize", track)
    try:
        with RecordingService(analysis_materializer=engine) as service:
            registered = [service.register_local_source(p) for p in paths]
            # 실행자가 ordinal 0을 명시했다. 카메라 역할이나 실제 overlap을 주장하지 않는다.
            videos = [[s for s in r.media_streams if s.media_type == "VIDEO"][0] for r in registered]
            rows = [dict(source_asset_ref=r.source_asset.source_asset_ref, media_stream_ref=v.media_stream_ref,
                timeline_start_sec=a, timeline_end_sec=b) for r, v, (a, b) in zip(registered, videos, bounds)]
            timeline = service.create_relative_timeline_from_placements(rows)
            boundary = bounds[1][0]
            resolution = service.resolve_span(dict(timeline_id=timeline.timeline_id, revision=timeline.revision),
                dict(start_sec=boundary-1, end_sec=boundary+1), media_stream_refs=[v.media_stream_ref for v in videos])
            assert resolution.status == "COMPLETE"
            source = service.prepare_analysis_source_from_resolution(resolution, "profile")
            assert attempted == [0, 1]
            with service.open_analysis_source(source.analysis_source_ref).stream as stream:
                assert len(stream.read()) == source.byte_size > 0
            assert all(str(p) not in source.model_dump_json() and p.name not in source.model_dump_json() for p in paths)
    finally:
        assert [fingerprint(p) for p in paths] == before
        assert not list(work.iterdir())


@pytest.mark.parametrize("delta,base,allowed", [
    (1/3000000, None, True), (-1/3000000, None, True),
    (0.000001, None, True), (-0.000001, None, True),
    (0.0000011, None, False), (-0.0000011, None, False),
    (0.1, None, False), (-0.1, None, False),
    (0.0000001, Fraction(1, 10000000), False),
    (-0.0000001, Fraction(1, 10000000), False),
])
def test_seam_serialization_tolerance_preserves_times(chain, monkeypatch, delta, base, allowed):
    service, resolution, paths, work, engine = chain
    before = [fingerprint(p) for p in paths]
    original = engine.materialize
    observations = []
    snapshot = resolution.model_dump()

    def decimal_observation(*args):
        out = original(*args)
        if args[2].sequence > 0:
            out = replace(out, timeline_range=out.timeline_range.model_copy(update={
                "start_sec": out.timeline_range.start_sec + delta,
                "end_sec": out.timeline_range.end_sec + delta}))
        if base is not None:
            out = replace(out, time_base=base)
        observations.append((out, out.timeline_range.model_dump(), out.frames))
        return out

    monkeypatch.setattr(engine, "materialize", decimal_observation)
    if allowed:
        result = service.prepare_analysis_source_from_resolution(resolution, "profile")
        assert result.duration_sec == 4.
        assert result.timeline_range.start_sec == 1.
        assert result.timeline_range.end_sec == 5. + delta
        assert result.timeline_ref == resolution.timeline_ref
    else:
        with pytest.raises(RecordingCapabilityError) as caught:
            service.prepare_analysis_source_from_resolution(resolution, "profile")
        assert caught.value.code == "UNSUPPORTED_MEDIA"
        assert not service._local_analysis
    assert resolution.model_dump() == snapshot
    assert all(out.timeline_range.model_dump() == ranges and out.frames == frames
               for out, ranges, frames in observations)
    assert [fingerprint(p) for p in paths] == before and not list(work.iterdir())


def test_h264_trailing_bad_packet_is_not_silently_ignored(tmp_path, monkeypatch):
    """실제 strict 실패가 관측된 환경에서만 오류 전달을 검증한다."""
    path = tmp_path / "synthetic-corrupt-tail.avi"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "lavfi", "-i",
        "testsrc2=s=64x48:r=30:d=2", "-c:v", "libx264", "-bf", "0", str(path)],
        capture_output=True, check=True, timeout=30)
    packets = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "0",
        "-show_packets", "-show_entries", "packet=pos,size", "-of", "json", str(path)],
        capture_output=True, check=True, timeout=30).stdout)["packets"]
    # 사용자 원본이 아닌 이 테스트에서 생성한 AVI의 마지막 packet만 손상시킨다.
    with path.open("r+b") as file:
        file.seek(int(packets[-1]["pos"]))
        file.write(bytes(int(packets[-1]["size"])))
    before = fingerprint(path)
    work = tmp_path / "work"
    work.mkdir()
    engine = LocalAnalysisMaterializer({"profile": AnalysisProfile(48, "veryfast", 23)}, temp_root=work)
    real_run, attempts = subprocess.run, []

    def capture_failure(args, **kwargs):
        result = real_run(args, **kwargs)
        if "-vf" in args:
            attempts.append(("-xerror" in args, result.returncode))
        return result

    monkeypatch.setattr(subprocess, "run", capture_failure)
    try:
        with RecordingService(analysis_materializer=engine) as service:
            registered = service.register_local_source(path)
            timeline = service.create_relative_timeline(registered.source_asset.source_asset_ref)
            ref = dict(timeline_id=timeline.timeline_id, revision=timeline.revision)
            resolution = service.resolve_span(ref, dict(start_sec=1., end_sec=1.9),
                media_stream_ref=registered.media_streams[0].media_stream_ref)
            assert resolution.status == "COMPLETE"
            caught = None
            try:
                service.prepare_analysis_source(resolution.spans[0], "profile", timeline_ref=ref)
            except RecordingCapabilityError as error:
                caught = error
            assert attempts and attempts[0][0]  # 항상 strict-first
            if not any(strict and code != 0 for strict, code in attempts):
                if caught is not None:
                    raise caught  # 무관한 출력 검증 실패 등을 skip으로 숨기지 않는다.
                pytest.skip("이 FFmpeg에서는 합성 packet의 strict encode 실패가 미관측됨; 정책 판단 제외")
            assert caught is not None
            assert caught.code in {"TEMPORARY_FAILURE", "UNSUPPORTED_MEDIA"}
            assert len(attempts) == 1  # RIFF 내부 손상을 후행 예외로 재시도하지 않는다.
            assert path.name not in str(caught) and str(path) not in str(caught)
            assert not service._local_analysis
    finally:
        assert fingerprint(path) == before and not list(work.iterdir())



def test_sub_microsecond_seams_do_not_accumulate(chain, monkeypatch):
    service, resolution, _, work, engine = chain
    original = engine.materialize

    def drift(*args):
        out = original(*args)
        delta = args[2].sequence * .00000075
        return replace(out, timeline_range=out.timeline_range.model_copy(update={
            "start_sec": out.timeline_range.start_sec + delta,
            "end_sec": out.timeline_range.end_sec + delta}))

    monkeypatch.setattr(engine, "materialize", drift)
    with pytest.raises(RecordingCapabilityError) as caught:
        service.prepare_analysis_source_from_resolution(resolution, "profile")
    assert caught.value.code == "UNSUPPORTED_MEDIA"
    assert "Timeline 길이" in str(caught.value)
    assert not service._local_analysis and not list(work.iterdir())
