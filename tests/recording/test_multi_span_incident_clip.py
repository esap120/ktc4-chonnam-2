"""다중 IncidentClip 공개 경로: strict 연결, provenance, 실패 미발급."""
from dataclasses import replace
import subprocess

import pytest

from daesingo.recording import LocalIncidentMaterializer, IncidentClipEncoding, RecordingCapabilityError
from daesingo.recording.analysis_tail import analysis_tail_scope, TailDecodeFailure
from tests.recording.test_multi_span_analysis_source import chain
from tests.recording.test_local_analysis_source import fingerprint


@pytest.fixture
def incident_chain(chain):
    service, resolution, paths, work, _ = chain
    adapter = LocalIncidentMaterializer(IncidentClipEncoding(48, "veryfast", 23), temp_root=work)
    service._incident_materializer = adapter
    return service, resolution, paths, work, adapter


@pytest.mark.parametrize("count", [2, 3])
def test_multi_clip_pixels_provenance_identity(incident_chain, tmp_path, count):
    service, original, paths, work, _ = incident_chain
    before = [fingerprint(p) for p in paths]
    resolution = service.resolve_span(original.timeline_ref, dict(start_sec=1., end_sec=float(2*count-1)),
        media_stream_refs=[s.media_stream_ref for s in original.spans])
    saved = resolution.model_dump()
    clip = service.build_incident_clip(resolution)
    assert len(clip.source_provenance.asset_spans) == count
    assert clip.source_provenance.asset_spans == resolution.spans
    assert clip.source_provenance.timeline_ref == resolution.timeline_ref == clip.timeline_ref
    assert clip.source_provenance.requested_range == resolution.requested_range == clip.timeline_range
    assert clip.media_stream_refs == [s.media_stream_ref for s in resolution.spans]
    assert clip.duration_sec == 2*count-2 and clip.availability == "AVAILABLE"
    content = service._local_clips[clip.incident_clip_ref][1]
    assert clip.byte_size == len(content) > 0
    output = tmp_path / "clip.mp4"
    output.write_bytes(content)
    decoded = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True, timeout=30).stdout
    frames = [decoded[i:i+64*48*3] for i in range(0, len(decoded), 64*48*3)]
    assert len(frames) == (2*count-2)*10
    for i, frame in enumerate(frames):
        r, g, b = frame[:3]
        assert (r > 230 and b < 10) if i < 10 else ((b > 230 and r < 10) if i < 30 else (g > 110 and r < 10))
    assert service.build_incident_clip(resolution).incident_clip_ref == clip.incident_clip_ref
    assert service.get_incident_clip(clip.incident_clip_ref) == clip
    assert resolution.model_dump() == saved and [fingerprint(p) for p in paths] == before
    assert not list(work.iterdir())


@pytest.mark.parametrize("bad", ["gap", "overlap", "reverse", "sequence", "duplicate", "missing", "changed"])
def test_invalid_chain_is_failed_not_published(incident_chain, bad):
    service, resolution, paths, work, _ = incident_chain
    data = resolution.model_dump()
    if bad == "gap": data["spans"][1]["timeline_range"]["start_sec"] += .1
    if bad == "overlap": data["spans"][1]["timeline_range"]["start_sec"] -= .1
    if bad == "reverse": data["spans"].reverse()
    if bad == "sequence":
        data["spans"].reverse()
        for i, span in enumerate(data["spans"]): span["sequence"] = i
    if bad == "duplicate": data["spans"][1] = dict(data["spans"][0], sequence=1)
    if bad == "missing": paths[1].unlink()
    if bad == "changed": paths[1].write_bytes(b"synthetic mutation")
    with pytest.raises(RecordingCapabilityError) as error: service.build_incident_clip(data)
    assert error.value.code == "INCIDENT_CLIP_BUILD_FAILED"
    assert not service._local_clips and not service._clip_identity and not list(work.iterdir())


@pytest.mark.parametrize("mode", ["encode", "concat", "timeout", "output", "coverage", "decode", "mutation"])
def test_strict_chain_failures_and_cleanup(incident_chain, monkeypatch, mode):
    service, resolution, paths, work, adapter = incident_chain
    engine = adapter._engine
    run, probe, materialize = engine._run, engine._probe, engine.materialize
    def checked_run(args):
        if "-vf" in args or "concat" in args: assert "-xerror" in args
        if mode == "encode" and "-vf" in args: raise TailDecodeFailure()
        if "concat" in args:
            if mode == "concat": raise RecordingCapabilityError("TEMPORARY_FAILURE", "private")
            if mode == "timeout": raise subprocess.TimeoutExpired(args, 1, stderr=b"private")
            if mode == "mutation": paths[0].write_bytes(b"synthetic mutation")
        return run(args)
    def checked_probe(path, index=None):
        raw = probe(path, index)
        if mode == "output" and path.parent.name.startswith("recording-chain-"): raw["frames"].pop()
        return raw
    def checked_materialize(*args):
        out = materialize(*args)
        if mode == "coverage" and args[2].sequence == 0:
            return replace(out, timeline_range=out.timeline_range.model_copy(update={"end_sec": out.timeline_range.end_sec-.1}))
        return out
    def forbidden(*args): pytest.fail("IncidentClip must not inspect best-effort")
    monkeypatch.setattr(engine, "_run", checked_run)
    monkeypatch.setattr(engine, "_probe", checked_probe)
    monkeypatch.setattr(engine, "materialize", checked_materialize)
    monkeypatch.setattr(engine, "_verify_tail", forbidden)
    if mode == "decode":
        def fail(*args): raise RecordingCapabilityError("TEMPORARY_FAILURE", "private")
        monkeypatch.setattr(engine, "_strict_decode", fail)
    with analysis_tail_scope(), pytest.raises(RecordingCapabilityError) as error:
        service.build_incident_clip(resolution)
    assert error.value.code == "INCIDENT_CLIP_BUILD_FAILED" and "private" not in str(error.value)
    assert not service._local_clips and not service._clip_identity and not list(work.iterdir())


def test_actual_timeline_gap_is_not_compressed(incident_chain):
    service, original, _, work, _ = incident_chain
    rows = [dict(source_asset_ref=s.source_asset_ref, media_stream_ref=s.media_stream_ref,
        timeline_start_sec=float(i*3), timeline_end_sec=float(i*3+2)) for i, s in enumerate(original.spans)]
    timeline = service.create_relative_timeline_from_placements(rows)
    resolution = service.resolve_span(dict(timeline_id=timeline.timeline_id, revision=timeline.revision),
        dict(start_sec=1., end_sec=7.), media_stream_refs=[s.media_stream_ref for s in original.spans])
    assert resolution.status == "PARTIAL" and len(resolution.missing_ranges) == 2
    with pytest.raises(RecordingCapabilityError) as error: service.build_incident_clip(resolution)
    assert error.value.code == "INCIDENT_CLIP_BUILD_FAILED"
    assert not service._local_clips and not list(work.iterdir())


def test_multi_identity_requires_same_revision_and_actual_bytes(incident_chain, monkeypatch):
    service, resolution, _, work, adapter = incident_chain
    first = service.build_incident_clip(resolution)
    timeline = service.get_timeline(resolution.timeline_ref.timeline_id, resolution.timeline_ref.revision)
    service._repository.add_timeline(timeline.model_copy(update={"revision": 2}))
    new = service.resolve_span(dict(timeline_id=timeline.timeline_id, revision=2),
        resolution.requested_range, media_stream_refs=[s.media_stream_ref for s in resolution.spans])
    second = service.build_incident_clip(new)
    original = adapter._materialize_many
    def different_bytes(*args):
        result = original(*args)
        return replace(result, content=result.content + b"\x00\x00\x00\x08free")
    monkeypatch.setattr(adapter, "_materialize_many", different_bytes)
    third = service.build_incident_clip(resolution)
    assert len({c.incident_clip_ref for c in (first, second, third)}) == 3
    assert service.get_incident_clip(first.incident_clip_ref) == first
    assert third.byte_size == first.byte_size + 8
    assert not list(work.iterdir())
