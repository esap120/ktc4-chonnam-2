#!/usr/bin/env python
"""실제 coarse->fine 구조(run_case)를 느린 영상으로 돌린다. 기본: Coarse 0.5x(원본 2fps) / Fine 0.25x(원본 4fps).

프록시는 영상을 재생 시간 1초당 1프레임·low(66토큰)로 재샘플링한다
(gemini-video-slowdown-token-probe-2026-09-29). 영상을 speed 배로 늘리면 원본 1초에
1/speed 프레임이 모델에 들어간다. 이미지 전송(프레임당 1,100토큰)보다 싸게 시간 밀도를 올린다.

구조: image trace 와 같이 run_case 의 provider seam 에 invoker 를 끼운다. MediaPreparer 가
fps=1/speed 로 준비한 MP4 를 invoker 가 setpts 로 늘려 영상(`type: file`)으로 보낸다.
모델은 늘어난 영상 기준 시각으로 답하고, invoker 가 speed 를 곱해 원본 시각으로 되돌린 뒤
run_case 에 넘긴다. 프롬프트·스키마·후보 핸드오프·padding·clamp 는 그대로다(p3).

1x 도 같은 invoker(재인코딩 없음)로 같은 실행에서 돌려 통제 비교한다.

--transport image 는 같은 조건을 이미지로 보낸다(gemini_coarse_fine_image_trace.ImageInvoker).
이때 배속 s 는 준비 fps 1/s 를 뜻한다(0.5:0.25 = Coarse 2fps / Fine 4fps).
--profiles 로 diagnostic-v1·diagnostic-handoff-v1 등을 같은 실행에서 비교한다.

실행(유료): uv run --extra eval-gemini python scripts/gemini_coarse_fine_slowdown_trace.py --out <json>
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.decision_trace import DiagnosticCoarseResponse, DiagnosticFineResponse
from daesingo.search.diagnostic import run_case
from daesingo.search.diagnostic_call import DiagnosticDependencies
from daesingo.search.diagnostic_models import DiagnosticCase, DiagnosticProfile
from daesingo.search.media import MediaPreparer
from daesingo.search.provider import (
    ProviderResult,
    StructuredInvocation,
    _usage_from_completion,
)
from daesingo.search.schemas import CoarseResponse, FineResponse
from daesingo.search.smoke_errors import ProviderApiError, ProviderPayloadError

VID = "C:/Users/User/orca/ktc4-chonnam-2/src/daesingo/search/video"
DEFAULT_ENV = "C:/Users/User/orca/ktc4-chonnam-2/.env"

# 정답지.md: (case_id, file, duration, event, 기대, 정답 구간들(원본 초) 또는 None)
CASES = [
    ("20260620_141628_EVT_1", "20260620_141628_EVT_1.avi", 20.023, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED", None),
    ("20260620_141927_EVT_1", "20260620_141927_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((4.0, 10.0),)),
    ("20260620_141956_EVT_1", "20260620_141956_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED", None),
    ("20260620_150504_EVT_1", "20260620_150504_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED", None),
    ("youtube_clip_01", "youtube_clip_01.mp4", 5.533, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((0.0, 2.0),)),
    ("YT_0003_C05", "YT_0003_C05.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((10.0, 12.0), (20.0, 22.0))),
    ("YT_0002_C00", "YT_0002_C00.mp4", 20.079, "CENTER_LINE_CROSSING", "OBSERVED", ((10.0, 14.0),)),
    # set1 g3 (2026-10-04). C47 은 onset 이 조각 경계 3초 이내(원래 채점 BOUNDARY_EXCLUDED).
    ("YT_0001_C08", "YT_0001_C08.mp4", 60.0, "SIGNAL", "OBSERVED", ((15.0, 17.8),)),
    ("YT_0001_C09", "YT_0001_C09.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((9.0, 11.0),)),
    ("YT_0001_C33", "YT_0001_C33.mp4", 60.0, "SIGNAL", "OBSERVED", ((50.0, 52.0),)),
    ("YT_0001_C39", "YT_0001_C39.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((52.0, 55.0),)),
    ("YT_0001_C47", "YT_0001_C47.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((0.5, 3.0),)),
    ("YT_0003_C10", "YT_0003_C10.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((7.0, 9.0),)),
    ("YT_0003_C28", "YT_0003_C28.mp4", 60.0, "CENTER_LINE_CROSSING", "OBSERVED", ((9.0, 10.0),)),
    ("YT_0003_C44", "YT_0003_C44.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED", ((28.0, 30.0),)),
]


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p is None:
        raise SystemExit("ffmpeg not found")
    return p


def _slow(src: Path, dest: Path, speed: float) -> None:
    """준비된 MP4(fps=1/speed)를 speed 배로 늘려 재생 1초 = 원본 프레임 1장이 되게 한다."""
    r = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(src), "-vf", f"setpts=PTS/{speed}",
         "-c:v", "libx264", "-an", "-movflags", "+faststart", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise ProviderPayloadError(f"slowdown failed: {r.stderr.decode(errors='replace')[-200:]}")


def _note(speed: float, handoff: bool) -> str:
    factor = round(1 / speed)
    extra = (
        f" Coarse 핵심 시각도 원본 기준이므로 제공 영상에서는 그 {factor}배 위치입니다."
        if handoff else ""
    )
    return (
        f"\n\n주의: 제공 영상은 원본을 {factor}배 느리게 재생하도록 늘린 것입니다. "
        f"위에 적힌 길이·구간은 원본 기준이고, 제공 영상의 길이는 그 {factor}배입니다. "
        "모든 시각은 제공 영상(느려진 영상) 기준으로 답하세요. "
        "움직임이 느려 보이는 것은 재생 속도 때문이며 판단 근거가 아닙니다."
        + extra
    )


def _to_origin(parsed, speed: float):
    """느려진 영상 기준 시각 -> 원본 기준 시각."""
    if speed == 1.0:
        return parsed
    if isinstance(parsed, (CoarseResponse, DiagnosticCoarseResponse)):
        cands = [
            c.model_copy(update={
                "at_sec": c.at_sec * speed,
                "span": c.span.model_copy(update={
                    "start_sec": c.span.start_sec * speed,
                    "end_sec": c.span.end_sec * speed,
                }),
            })
            for c in parsed.candidates
        ]
        update: dict = {"candidates": cands}
        if isinstance(parsed, DiagnosticCoarseResponse):
            update["window_reviews"] = [
                w.model_copy(update={"start_sec": w.start_sec * speed,
                                     "end_sec": w.end_sec * speed})
                for w in parsed.window_reviews
            ]
        return parsed.model_copy(update=update)
    if isinstance(parsed, FineResponse):
        def scale(items):
            return [i.model_copy(update={"at_offset_ms": None if i.at_offset_ms is None
                                         else round(i.at_offset_ms * speed)})
                    for i in items]
        update = {"temporal_facts": scale(parsed.temporal_facts)}
        if isinstance(parsed, DiagnosticFineResponse):
            update["decision_basis"] = scale(parsed.decision_basis)
        return parsed.model_copy(update=update)
    raise ProviderPayloadError(f"unexpected response type {type(parsed).__name__}")


class SlowVideoInvoker:
    """StructuredInvoker: 준비 미디어를 speed 배로 늘려 영상으로 보내고 시각을 원본으로 환산."""

    def __init__(self, client, config: GeminiSearchConfig,
                 coarse_speed: float, fine_speed: float) -> None:
        self._client = client
        self._cfg = config
        self._coarse_speed = coarse_speed
        self._fine_speed = fine_speed

    def invoke_structured(self, request: StructuredInvocation) -> ProviderResult:
        coarse = issubclass(request.response_model, (CoarseResponse, DiagnosticCoarseResponse))
        speed = self._coarse_speed if coarse else self._fine_speed
        with tempfile.TemporaryDirectory(prefix="cf_slow_") as td:
            path = request.media.path
            prompt = request.prompt
            if speed != 1.0:
                # MediaPreparer 가 이미 1/fps 배로 늘려 준다(2026-10-01 운영 반영). 그때는 다시 늘리지 않는다.
                if request.media.playback_speed == 1.0:
                    path = Path(td) / "slow.mp4"
                    _slow(request.media.path, path, speed)
                prompt += _note(speed, "Coarse 핵심 시각" in prompt)
            url = "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "file", "file": {"file_data": url}},
            ]}]
            started = time.monotonic()
            try:
                # 프록시는 non-streaming 응답을 2,000토큰으로 자른다(medium·high 는 사고 토큰만으로
                # 넘는다). 스트리밍이면 상한이 풀린다. 응답 내용은 같고 전달 방식만 다르다.
                with self._client.chat.completions.stream(
                    model=self._cfg.model, messages=messages,
                    response_format=request.response_model,
                    reasoning_effort=self._cfg.reasoning_effort,
                    max_tokens=16384, stream_options={"include_usage": True},
                    timeout=request.timeout_sec,
                ) as stream:
                    comp = stream.get_final_completion()
            except Exception as exc:  # noqa: BLE001
                from openai import APIError, BadRequestError
                if isinstance(exc, BadRequestError):
                    raise ProviderPayloadError("provider rejected the request") from exc
                if isinstance(exc, APIError):
                    raise ProviderApiError("provider API error") from exc
                raise ProviderPayloadError(f"invoke failed: {exc}") from exc
            latency = round((time.monotonic() - started) * 1000)
            parsed = comp.choices[0].message.parsed
            if parsed is None:
                raise ProviderPayloadError("provider returned no parsed content")
            return ProviderResult(
                _to_origin(parsed, speed),
                _usage_from_completion(getattr(comp, "usage", None)),
                latency,
            )


def _overlaps(span: tuple[float, float], truth: tuple[tuple[float, float], ...] | None) -> bool:
    return truth is not None and any(span[0] < t[1] and t[0] < span[1] for t in truth)


def run_condition(client, base_cfg: GeminiSearchConfig, coarse_speed: float,
                  fine_speed: float, timeout: float,
                  profile: DiagnosticProfile = DiagnosticProfile.P3,
                  transport: str = "video") -> dict:
    # 준비 fps = 1/speed -> 늘린 뒤 재생 1초당 원본 프레임 1장(프록시 샘플링과 1:1).
    # image 는 늘리지 않고 그 fps 프레임을 전량 image_url 로 보낸다.
    cfg = replace(base_cfg, coarse_fps=1 / coarse_speed, fine_fps=1 / fine_speed, max_retries=0)
    if transport == "image":
        from gemini_coarse_fine_image_trace import ImageInvoker
        invoker = ImageInvoker(client, cfg)
    elif transport == "provider":
        # 운영 경로 그대로: MediaPreparer 가 늘리고 GeminiProvider 가 안내·시각 환산을 한다.
        from daesingo.search.provider import GeminiProvider, ProviderRuntimeOptions
        invoker = GeminiProvider(client.api_key, cfg,
                                 runtime=ProviderRuntimeOptions(request_timeout_sec=timeout))
    else:
        invoker = SlowVideoInvoker(client, cfg, coarse_speed, fine_speed)
    deps = DiagnosticDependencies(invoker, MediaPreparer(cfg), cfg, profile, timeout)
    tag = f"{profile.value}/{transport}/{coarse_speed}x/{fine_speed}x"
    verifs: Counter[str] = Counter()
    cases = []
    invocations = prompt_tok = total_tok = 0
    latencies: dict[str, list[int]] = {"COARSE": [], "FINE": []}
    for cid, fname, dur, event, expected, truth in CASES:
        case = DiagnosticCase(case_id=cid, source=Path(VID) / fname,
                              duration_sec=dur, event_types=(event,))
        res = run_case(case, deps)
        cands, fine, fine_responses = [], [], []
        for call in res.calls:
            if call.status == "SUCCEEDED":
                invocations += 1
                if call.latency_ms is not None:
                    latencies[call.stage].append(call.latency_ms)
                if call.usage:
                    prompt_tok += call.usage.input_tokens or 0
                    total_tok += call.usage.total_tokens or 0
            if call.stage == "COARSE" and isinstance(call.response, (CoarseResponse, DiagnosticCoarseResponse)):
                for c in sorted(call.response.candidates, key=lambda c: (-c.score, c.at_sec)):
                    span = (round(c.span.start_sec, 2), round(c.span.end_sec, 2))
                    cands.append({"span": span, "at_sec": round(c.at_sec, 2),
                                  "hits_truth": _overlaps(span, truth),
                                  "score": c.score, "observed": list(c.observed)})
            if call.stage == "FINE":
                v = getattr(call.response, "verification", None) if call.response else None
                label = v.value if v is not None else f"FAILED:{','.join(call.issue_codes)}"
                verifs[label if v is not None else "FAILED"] += 1
                fine.append(label)
                fine_responses.append(call.response.model_dump(mode="json") if call.response else None)
        # 클립 판정: 정답 구간과 겹친 후보가 OBSERVED 면 검출. 음성 클립은 OBSERVED 가 하나라도 있으면 오탐.
        if expected == "OBSERVED":
            detected = any(c["hits_truth"] and i < len(fine) and fine[i] == "OBSERVED"
                           for i, c in enumerate(cands))
            verdict = "HIT" if detected else "MISS"
        else:
            verdict = "FALSE_POSITIVE" if "OBSERVED" in fine else "CORRECT_REJECT"
        cases.append({"case_id": cid, "event": event, "expected": expected, "truth": truth,
                      "candidates": cands, "fine": fine, "fine_responses": fine_responses,
                      "verdict": verdict,
                      "issue_codes": sorted({ic for c in res.calls for ic in c.issue_codes})})
        print(f"  [{tag}] {cid:<24} cand={[c['span'] for c in cands]} fine={fine} -> {verdict}")
    return {
        "profile": profile.value, "transport": transport,
        "coarse_speed": coarse_speed, "fine_speed": fine_speed,
        "coarse_fps_prepared": cfg.coarse_fps, "fine_fps_prepared": cfg.fine_fps,
        "invocations": invocations, "verification_counts": dict(verifs),
        "reported_input_tokens": prompt_tok, "reported_total_tokens": total_tok,
        "provider_latency_ms": latencies,
        "positives_hit": sum(c["verdict"] == "HIT" for c in cases),
        "negatives_correct": sum(c["verdict"] == "CORRECT_REJECT" for c in cases),
        "cases": cases,
    }


def _patch_fine_height(height: int) -> None:
    # ponytail: 운영 media.py 를 고치지 않으려고 모듈 함수를 바꿔 끼운다. 운영에 넣을 때는 config 값으로.
    from daesingo.search import media
    original = media._run_ffmpeg_encode

    def encode(*a, max_height: int, start_sec: float | None = None, **kw):
        if start_sec is not None:  # Fine 준비만 구간(start_sec)을 받는다
            max_height = height
        return original(*a, max_height=max_height, start_sec=start_sec, **kw)

    media._run_ffmpeg_encode = encode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--timeout-sec", type=float, default=300.0)
    # coarse:fine 배속. 기본 = 1x 기준 + 이미지 trace(coarse 2fps / fine 4fps)와 같은 밀도.
    ap.add_argument("--conditions", default="1:1,0.5:0.25")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--profiles", default="p3")
    ap.add_argument("--transport", choices=("video", "image", "provider"), default="video")
    ap.add_argument("--reasoning", default=None,
                    help="쉼표로 나눈 reasoning_effort 값들(video transport 만 스트리밍). 없으면 설정값")
    ap.add_argument("--clips", default=None, help="쉼표로 나눈 case_id 앞부분으로 거른다")
    ap.add_argument("--fine-height", type=int, default=None,
                    help="Fine 준비 영상 최대 높이(운영 MediaPreparer 는 360 고정). 실험에서만 바꾼다")
    args = ap.parse_args()
    if args.clips:
        CASES[:] = [c for c in CASES if c[0].startswith(tuple(args.clips.split(",")))]

    if args.fine_height:
        _patch_fine_height(args.fine_height)
    env = load_env_file(args.env)
    base_cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=base_cfg.base_url, api_key=key, max_retries=0, timeout=args.timeout_sec
    )
    efforts = args.reasoning.split(",") if args.reasoning else [base_cfg.reasoning_effort]
    runs = []
    for rep in range(args.repeats):
        for cond, prof, effort in ((c, p, e) for c in args.conditions.split(",")
                                   for p in args.profiles.split(",") for e in efforts):
            cs, fs = (float(x) for x in cond.split(":"))
            print(f"=== repeat {rep + 1} / {prof} / {args.transport} / {effort} / coarse {cs}x, fine {fs}x ===")
            started = time.monotonic()
            r = run_condition(client, replace(base_cfg, reasoning_effort=effort), cs, fs,
                              args.timeout_sec, DiagnosticProfile(prof), args.transport)
            r["repeat"] = rep + 1
            r["reasoning_effort"] = effort
            r["wall_sec"] = round(time.monotonic() - started, 1)
            runs.append(r)
            n_pos = sum(c["expected"] == "OBSERVED" for c in r["cases"])
            print(f"  -> [{effort}] {r['wall_sec']}s positives {r['positives_hit']}/{n_pos}, "
                  f"negatives {r['negatives_correct']}/{len(r['cases']) - n_pos}, "
                  f"fine {r['verification_counts']}, input_tok {r['reported_input_tokens']}, "
                  f"total_tok {r['reported_total_tokens']}")
            if args.out:  # 조건마다 저장해 중간에 끊겨도 남긴다
                args.out.write_text(json.dumps({
                    "config": {"profiles": args.profiles, "transport": args.transport, "model": base_cfg.model, "fine_height": args.fine_height or 360,
                               "reasoning_efforts": efforts,
                               "fine_padding_sec": base_cfg.fine_padding_sec},
                    "runs": runs}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
