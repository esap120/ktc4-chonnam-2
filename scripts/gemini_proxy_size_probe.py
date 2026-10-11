#!/usr/bin/env python
"""프록시가 받아 주는 인라인 영상 요청의 실제 크기 한도는 얼마인가.

config.py 의 max_inline_media_bytes(12 MiB)·max_inline_request_bytes(18 MiB)는 근거 없이
정한 값이다. 영상 토큰은 재생 길이로만 정해지므로(재생 초 × 66), 10초 영상을 노이즈와
고정 비트레이트로 크게 만들어 크기만 바꿔 보낸다. 응답 상태·오류·지연·토큰만 남긴다.
실행(유료, 호출당 약 700토큰): uv run --extra eval-gemini python scripts/gemini_proxy_size_probe.py --out <json>
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from gemini_coarse_fine_slowdown_trace import DEFAULT_ENV, VID, _ffmpeg

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env

SOURCE = "20260620_141927_EVT_1.avi"
DURATION = 10.0
TARGET_MB = [11, 15, 25, 40, 60]


def _make(size_mb: int, dest: Path) -> Path:
    kbps = round(size_mb * 8 * 1024 / DURATION)
    r = subprocess.run(
        [_ffmpeg(), "-y", "-t", str(DURATION), "-i", str(Path(VID) / SOURCE), "-an",
         "-vf", "noise=alls=60:allf=t", "-c:v", "libx264", "-preset", "veryfast",
         "-b:v", f"{kbps}k", "-minrate", f"{kbps}k", "-maxrate", f"{kbps}k",
         "-bufsize", f"{kbps}k", "-movflags", "+faststart", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=600.0
    )

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="size_") as td:
        for mb in TARGET_MB:
            path = _make(mb, Path(td) / f"{mb}.mp4")
            url = "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode()
            messages = [{"role": "user", "content": [
                {"type": "text", "text": "Reply with the single word OK."},
                {"type": "file", "file": {"file_data": url}},
            ]}]
            request_bytes = len(json.dumps({"model": cfg.model, "messages": messages}))
            row = {"target_mb": mb, "media_bytes": path.stat().st_size,
                   "media_mib": round(path.stat().st_size / 2**20, 2),
                   "request_mib": round(request_bytes / 2**20, 2)}
            t0 = time.monotonic()
            try:
                comp = client.chat.completions.create(
                    model=cfg.model, messages=messages,
                    reasoning_effort=cfg.reasoning_effort,
                )
                row |= {"status": "OK",
                        "input_tokens": getattr(comp.usage, "prompt_tokens", None)}
            except Exception as exc:  # noqa: BLE001 — 거절 자체가 측정 대상이다
                row |= {"status": type(exc).__name__,
                        "http_status": getattr(exc, "status_code", None),
                        "error": str(exc)[:300]}
            row["latency_sec"] = round(time.monotonic() - t0, 2)
            rows.append(row)
            print(f"  media={row['media_mib']} MiB request={row['request_mib']} MiB "
                  f"-> {row['status']} {row.get('http_status') or ''} "
                  f"tokens={row.get('input_tokens')} {row['latency_sec']}s")
            args.out.write_text(json.dumps({"model": cfg.model, "rows": rows},
                                           ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
