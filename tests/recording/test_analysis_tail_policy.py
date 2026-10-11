"""후행 packet 허용은 Search capability에만 한정한다."""
from copy import deepcopy
import logging
import subprocess

import pytest

from daesingo.recording import RecordingCapabilityError
from tests.recording.test_local_analysis_source import media, setup, span_for, fingerprint
from tests.recording.test_multi_span_analysis_source import chain


def evidence():
    return dict(streams=[dict(codec_name="h264", has_b_frames=0)],
        format=dict(format_name="avi"), packets_and_frames=[
            dict(type="packet", pos="100", size="40", pts=0),
            dict(type="frame", pkt_pos="100", pkt_size="40", best_effort_timestamp=0),
            dict(type="packet", pos="150", size="40", pts=1),
            dict(type="frame", pkt_pos="150", pkt_size="40", best_effort_timestamp=1),
            dict(type="packet", pos="300", size="16", pts=2)])


@pytest.mark.parametrize("flags", [None, 0, 1])
def test_decode_error_flags_observation_is_explicit(flags):
    from daesingo.recording.analysis_tail import validate_tail
    data, audit = evidence(), {}
    if flags is not None:
        for row in data["packets_and_frames"]:
            if row["type"] == "frame": row["decode_error_flags"] = flags
    if flags == 1:
        with pytest.raises(ValueError): validate_tail(data, 200, 400, [0, 1], audit=audit)
    else:
        assert validate_tail(data, 200, 400, [0, 1], audit=audit) == 1
    assert audit["decode_error_flags_observed"] is (flags is not None)


@pytest.mark.parametrize("case", ["tail_inside_frame_packet", "packet_overlap", "adjacent_tail"])
def test_packet_byte_intervals(case):
    from daesingo.recording.analysis_tail import validate_tail
    data, riff_end = evidence(), 170
    if case == "tail_inside_frame_packet": data["packets_and_frames"][-1]["pos"] = "180"
    if case == "packet_overlap":
        data["packets_and_frames"][0]["size"] = "60"
        data["packets_and_frames"][1]["pkt_size"] = "60"
    if case == "adjacent_tail":
        data["packets_and_frames"][-1]["pos"] = "190"
        assert validate_tail(data, riff_end, 400, [0, 1]) == 1
    else:
        with pytest.raises(ValueError): validate_tail(data, riff_end, 400, [0, 1])


@pytest.mark.parametrize("bad", ["inside_riff", "frame_after_error"])
def test_internal_packet_is_not_a_tail_exception(bad):
    from daesingo.recording.analysis_tail import validate_tail
    data = evidence()
    if bad == "inside_riff":
        data["packets_and_frames"][-1]["pos"] = "190"
    else:
        data["packets_and_frames"] += [
            dict(type="packet", pos="330", size="40", pts=2),
            dict(type="frame", pkt_pos="330", pkt_size="40", best_effort_timestamp=2)]
    with pytest.raises(ValueError):
        validate_tail(data, 200, 400, [0, 1] if bad == "inside_riff" else [0, 1, 2])


@pytest.mark.parametrize("tail_candidate", [False, True])
def test_subprocess_failure_policy_is_platform_independent(media, tmp_path, monkeypatch, tail_candidate):
    from daesingo.recording.analysis_tail import validate_tail
    service, _, registered, ref, profile, engine, work = setup(media, tmp_path)
    video = [s for s in registered.media_streams if s.media_type == "VIDEO"][0]
    span = span_for(service, ref, video, 0, 1)
    before, real_run, attempts, inspections = fingerprint(media), subprocess.run, [], []
    def run(args, **kwargs):
        if "-vf" in args:
            attempts.append("-xerror" in args)
            stderr = (b"No start code is found. Error submitting packet to decoder" if tail_candidate
                      else b"synthetic encoder failure")
            return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=stderr)
        return real_run(args, **kwargs)
    def verify(*args):
        inspections.append(True)
        data = evidence()
        data["packets_and_frames"][-1]["pos"] = "190"  # RIFF 내부 packet
        return validate_tail(data, 200, 400, [0, 1], audit=args[-1])
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(engine, "_verify_tail", verify)
    with service, pytest.raises(RecordingCapabilityError) as caught:
        service.prepare_analysis_source(span, profile, timeline_ref=ref)
    assert caught.value.code == ("UNSUPPORTED_MEDIA" if tail_candidate else "TEMPORARY_FAILURE")
    assert attempts == [True] and inspections == ([True] if tail_candidate else [])
    assert not service._local_analysis and not service._analysis_reuse
    assert fingerprint(media) == before and not list(work.iterdir())


@pytest.mark.parametrize("bad", [None, "interior", "missing", "flags", "size", "duplicate", "bframes"])
def test_tail_evidence_fail_closed(bad):
    from daesingo.recording.analysis_tail import validate_tail
    data = deepcopy(evidence())
    if bad == "interior": data["packets_and_frames"][-1]["pos"] = "120"
    if bad == "missing": del data["packets_and_frames"][1]["pkt_pos"]
    if bad == "flags": data["packets_and_frames"][1]["decode_error_flags"] = 1
    if bad == "size": data["packets_and_frames"][-1]["size"] = "50"
    if bad == "duplicate": data["packets_and_frames"].append(data["packets_and_frames"][0])
    if bad == "bframes": data["streams"][0]["has_b_frames"] = 1
    if bad:
        with pytest.raises(ValueError): validate_tail(data, 200, 400, [0, 1])
    else:
        assert validate_tail(data, 200, 400, [0, 1]) == 1


def test_public_analysis_retries_only_verified_tail(media, tmp_path, monkeypatch, caplog):
    service, _, registered, ref, profile, engine, work = setup(media, tmp_path)
    video = [s for s in registered.media_streams if s.media_type == "VIDEO"][0]
    span = span_for(service, ref, video, 0, 1)
    before = fingerprint(media)
    original = engine._run
    attempts = []
    def run(args):
        if "-vf" in args:
            attempts.append("-xerror" in args)
            if "-xerror" in args:
                from daesingo.recording.analysis_tail import TailDecodeFailure
                raise TailDecodeFailure()
        return original(args)
    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "_verify_tail", lambda *args: 2, raising=False)
    with caplog.at_level(logging.INFO, logger="daesingo.recording.analysis_tail"):
        result = service.prepare_analysis_source(span, profile, timeline_ref=ref)
    assert attempts == [True, False]
    assert result.byte_size > 0
    with service.open_analysis_source(result.analysis_source_ref).stream as stream:
        assert len(stream.read()) == result.byte_size
    assert fingerprint(media) == before and not list(work.iterdir())
    assert "\"best_effort\": true" in caplog.text
    assert "\"decode_error_flags_observed\": false" in caplog.text
    assert str(media) not in caplog.text and media.name not in caplog.text


@pytest.mark.parametrize("mode", ["unknown", "evidence", "ordinal", "count", "pts", "duration", "decode", "mutation", "retry", "timeout"])
def test_failed_fallback_never_published_or_cached(media, tmp_path, monkeypatch, mode):
    from daesingo.recording.analysis_tail import TailDecodeFailure
    import subprocess
    service, _, registered, ref, profile, engine, work = setup(media, tmp_path)
    ordinal = 1 if mode == "ordinal" else 0
    video = [s for s in registered.media_streams if s.media_type == "VIDEO"][ordinal]
    span = span_for(service, ref, video, 0, 1)
    original_run, original_probe = engine._run, engine._probe
    calls = []
    def run(args):
        if "-vf" in args:
            calls.append("-xerror" in args)
            if "-xerror" in args:
                if mode == "unknown": raise RecordingCapabilityError("TEMPORARY_FAILURE", "도구 실패")
                raise TailDecodeFailure()
            if mode == "retry": raise RecordingCapabilityError("TEMPORARY_FAILURE", "도구 실패")
            if mode == "timeout": raise subprocess.TimeoutExpired(args, 1, stderr=b"private")
        return original_run(args)
    def verify(*args):
        if mode == "evidence": raise ValueError("검증 근거 없음")
        return 1
    def probe(path, index=None):
        result = original_probe(path, index)
        if index is None:
            if mode == "count": result["frames"].pop()
            if mode == "pts": result["frames"][1]["best_effort_timestamp"] += 1
            if mode == "duration": result["frames"][-1]["duration"] += 1
        return result
    original_decode = engine._strict_decode
    def decode(path):
        if mode == "decode": raise RecordingCapabilityError("TEMPORARY_FAILURE", "출력 decode 실패")
        original_decode(path)
        if mode == "mutation": media.write_bytes(b"synthetic mutation")
    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "_probe", probe)
    if mode != "ordinal": monkeypatch.setattr(engine, "_verify_tail", verify)
    monkeypatch.setattr(engine, "_strict_decode", decode)
    with pytest.raises(RecordingCapabilityError):
        service.prepare_analysis_source(span, profile, timeline_ref=ref)
    assert not service._local_analysis and not service._analysis_reuse
    assert not service._source_inspections._entries and not list(work.iterdir())
    assert calls == ([True] if mode in {"unknown", "evidence", "ordinal"} else [True, False])


def test_incident_remains_strict_even_inside_analysis_scope(media, tmp_path, monkeypatch):
    from daesingo.recording import RecordingService, LocalIncidentMaterializer, IncidentClipEncoding
    from daesingo.recording.analysis_tail import TailDecodeFailure, analysis_tail_scope
    adapter = LocalIncidentMaterializer(IncidentClipEncoding(48, "veryfast", 23), temp_root=tmp_path)
    calls = []
    original = adapter._engine._run
    def run(args):
        if "-vf" in args:
            calls.append("-xerror" in args)
            raise TailDecodeFailure()
        return original(args)
    def forbidden(*args): pytest.fail("IncidentClip must never inspect a fallback")
    monkeypatch.setattr(adapter._engine, "_run", run)
    monkeypatch.setattr(adapter._engine, "_verify_tail", forbidden)
    with RecordingService(incident_materializer=adapter) as service:
        registered = service.register_local_source(media)
        timeline = service.create_relative_timeline(registered.source_asset.source_asset_ref)
        ref = dict(timeline_id=timeline.timeline_id, revision=1)
        video = [s for s in registered.media_streams if s.media_type == "VIDEO"][0]
        resolution = service.resolve_span(ref, dict(start_sec=0., end_sec=1.), media_stream_ref=video.media_stream_ref)
        with analysis_tail_scope(), pytest.raises(RecordingCapabilityError) as error:
            service.build_incident_clip(resolution)
        assert error.value.code == "INCIDENT_CLIP_BUILD_FAILED"
        assert not service._local_clips
    assert calls == [True]
    assert not list(tmp_path.glob("recording-analysis-*"))


def test_packet_dts_is_observed_only_without_b_frames():
    from daesingo.recording.analysis_tail import validate_tail
    data = evidence()
    for row in data["packets_and_frames"]:
        if row["type"] == "packet": row["dts"] = row.pop("pts")
    assert validate_tail(data, 200, 400, [0, 1]) == 1
    data["packets_and_frames"][0]["dts"] = 1
    with pytest.raises(ValueError): validate_tail(data, 200, 400, [0, 1])


@pytest.mark.parametrize("fail_final", [False, True])
def test_multi_span_fallback_and_final_strict_decode(chain, monkeypatch, fail_final):
    from daesingo.recording.analysis_tail import TailDecodeFailure
    service, resolution, paths, work, engine = chain
    before = [fingerprint(p) for p in paths]
    original_run, original_decode = engine._run, engine._strict_decode
    calls, decodes = [], []
    def run(args):
        if "-vf" in args:
            calls.append("-xerror" in args)
            if "-xerror" in args: raise TailDecodeFailure()
        return original_run(args)
    def decode(path):
        is_final = path.parent.name.startswith("recording-chain-")
        decodes.append(is_final)
        if is_final and fail_final:
            raise RecordingCapabilityError("TEMPORARY_FAILURE", "출력 검증 실패")
        return original_decode(path)
    monkeypatch.setattr(engine, "_run", run)
    monkeypatch.setattr(engine, "_verify_tail", lambda *args: 1)
    monkeypatch.setattr(engine, "_strict_decode", decode)
    if fail_final:
        with pytest.raises(RecordingCapabilityError):
            service.prepare_analysis_source_from_resolution(resolution, "profile")
        assert not service._local_analysis and not service._analysis_reuse
    else:
        out = service.prepare_analysis_source_from_resolution(resolution, "profile")
        assert out.duration_sec == 4 and len(out.source_refs) == 3
    assert calls == [True, False] * 3 and decodes == [False] * 3 + [True]
    assert [fingerprint(p) for p in paths] == before and not list(work.iterdir())
