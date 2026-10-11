#!/usr/bin/env python
"""실제 coarse->fine 구조(run_case)를 이미지 전송으로 돌린다. Coarse 2fps / Fine 4fps.

진단 러너(diagnostic.run_case)는 provider(StructuredInvoker) seam 하나로 Coarse·Fine
을 다 태운다. 여기에 프레임을 image_url 로 보내는 invoker 를 끼우면, 프롬프트·스키마·
후보 핸드오프·padding·clamp 를 재구현하지 않고 실제 구조 그대로 이미지로 돈다.

비교군: docs/.../decision-trace-seven-video-2026-09-26-results.json 의 p3 run
(영상, coarse 1fps/fine 2fps -> 프록시가 1fps low 로 강제). profile 은 동일하게 p3.
변경점은 전송(이미지) 과 fps(coarse 2/fine 4) 뿐.

실행(유료): uv run --extra eval-gemini python scripts/gemini_coarse_fine_image_trace.py
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
from daesingo.search.diagnostic import run_case
from daesingo.search.diagnostic_call import DiagnosticDependencies
from daesingo.search.diagnostic_models import DiagnosticCase, DiagnosticProfile
from daesingo.search.media import MediaPreparer
from daesingo.search.provider import (
    ProviderResult,
    StructuredInvocation,
    _usage_from_completion,
)
from daesingo.search.smoke_errors import ProviderApiError, ProviderPayloadError

VID = "C:/Users/User/orca/ktc4-chonnam-2/src/daesingo/search/video"
DEFAULT_ENV = "C:/Users/User/orca/ktc4-chonnam-2/.env"

# 정답지.md 의 clip -> (duration, event_type, 기대). 이전 seven-video 와 같은 7클립.
CASES = [
    ("20260620_141628_EVT_1", "20260620_141628_EVT_1.avi", 20.023, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED"),
    ("20260620_141927_EVT_1", "20260620_141927_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "OBSERVED"),
    ("20260620_141956_EVT_1", "20260620_141956_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED"),
    ("20260620_150504_EVT_1", "20260620_150504_EVT_1.avi", 20.025, "SOLID_LINE_LANE_CHANGE", "NOT_OBSERVED"),
    ("youtube_clip_01", "youtube_clip_01.mp4", 5.533, "SOLID_LINE_LANE_CHANGE", "OBSERVED"),
    ("YT_0003_C05", "YT_0003_C05.mp4", 60.0, "SOLID_LINE_LANE_CHANGE", "OBSERVED"),
    ("YT_0002_C00", "YT_0002_C00.mp4", 20.079, "CENTER_LINE_CROSSING", "OBSERVED"),
]


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p is None:
        raise SystemExit("ffmpeg not found")
    return p


def _frames(mp4: Path, outdir: Path) -> list[Path]:
    """준비된 MP4 의 모든 프레임을 추출(이미 coarse2/fine4 fps 로 인코딩됨)."""
    outdir.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(mp4), "-qscale:v", "2", str(outdir / "f_%03d.jpg")],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise ProviderPayloadError(f"frame extract failed: {r.stderr.decode(errors='replace')[-200:]}")
    return sorted(outdir.glob("f_*.jpg"))


class ImageInvoker:
    """StructuredInvoker: 준비 미디어의 프레임을 image_url 로 보내 구조화 응답을 받는다."""

    def __init__(self, client, config: GeminiSearchConfig) -> None:
        self._client = client
        self._cfg = config

    def invoke_structured(self, request: StructuredInvocation) -> ProviderResult:
        with tempfile.TemporaryDirectory(prefix="cf_img_") as td:
            frames = _frames(request.media.path, Path(td))
            content: list[dict] = [{"type": "text", "text": request.prompt}]
            for f in frames:
                url = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
                content.append({"type": "image_url", "image_url": {"url": url}})
            messages = [{"role": "user", "content": content}]
            started = time.monotonic()
            try:
                comp = self._client.chat.completions.parse(
                    model=self._cfg.model, messages=messages,
                    response_format=request.response_model,
                    reasoning_effort=self._cfg.reasoning_effort,
                    timeout=request.timeout_sec,
                )
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
            return ProviderResult(parsed, _usage_from_completion(getattr(comp, "usage", None)), latency)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--timeout-sec", type=float, default=300.0)
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = replace(
        GeminiSearchConfig.from_dotenv(env),
        coarse_fps=2.0, fine_fps=4.0, max_retries=0,
    )
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=args.timeout_sec
    )
    deps = DiagnosticDependencies(
        ImageInvoker(client, cfg), MediaPreparer(cfg), cfg,
        DiagnosticProfile.P3, args.timeout_sec,
    )

    case_results = []
    verifs: Counter[str] = Counter()
    invocations = 0
    total_tokens = 0
    for cid, fname, dur, event, expected in CASES:
        src = Path(VID) / fname
        case = DiagnosticCase(case_id=cid, source=src, duration_sec=dur, event_types=(event,))
        res = run_case(case, deps)
        fine_verifs = []
        for call in res.calls:
            if call.status == "SUCCEEDED":
                invocations += 1
                if call.usage and call.usage.total_tokens:
                    total_tokens += call.usage.total_tokens
            if call.stage == "FINE" and call.response is not None:
                v = getattr(call.response, "verification", None)
                if v is not None:
                    verifs[v.value] += 1
                    fine_verifs.append(v.value)
        n_cand = sum(1 for c in res.calls if c.stage == "FINE")
        coarse_ok = any(c.stage == "COARSE" and c.status == "SUCCEEDED" for c in res.calls)
        case_results.append({
            "case_id": cid, "event": event, "expected": expected,
            "coarse_succeeded": coarse_ok, "n_candidates": n_cand,
            "fine_verifications": fine_verifs,
            "issue_codes": sorted({ic for c in res.calls for ic in c.issue_codes}),
        })
        print(f"  {cid:<24} ev={event:<22} cand={n_cand} fine={fine_verifs} exp={expected}")

    summary = {
        "config": {"profile": "p3", "transport": "image", "coarse_fps": 2.0, "fine_fps": 4.0,
                   "model": cfg.model, "reasoning_effort": cfg.reasoning_effort},
        "invocations": invocations,
        "verification_counts": dict(verifs),
        "reported_total_tokens": total_tokens,
        "cases": case_results,
        "baseline_p3_video": {"invocations": 16, "verification_counts": {"NOT_OBSERVED": 7, "OBSERVED": 2},
                              "reported_total_tokens": 28607, "coarse_fps": 1.0, "fine_fps": 2.0},
    }
    print("\n=== summary (image coarse2/fine4) ===")
    print(f"  invocations: {invocations} | verification_counts: {dict(verifs)} | total_tokens: {total_tokens}")
    print(f"  baseline p3(video): invocations 16 | {{'NOT_OBSERVED':7,'OBSERVED':2}} | 28607 tok")

    if args.out:
        args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
