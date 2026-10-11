#!/usr/bin/env python
"""영상을 느리게(0.5x·0.25x) 만들면 프록시가 보는 프레임 수가 늘어나는가.

gemini-proxy-video-sampling-2026-09-28 실험의 배속판. 프록시는 영상을 재생 시간 1초당
1프레임·low(66토큰)로 재샘플링했다. 재생 시간을 늘리면 원본 1초에서 더 많은 프레임이
모델에 들어가는지 확인한다. 방법은 같다: 고정 프롬프트를 영상 없이 보낸 입력 토큰을
빼서 영상 토큰으로 본다. 요청 형식은 provider.py 와 같은 `type: file` base64 인라인.

실행(유료 호출): uv run python scripts/gemini_video_slowdown_token_probe.py --out <json>
영상/키는 저장하지 않는다.
"""

from __future__ import annotations

import argparse
import base64
import importlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env

PROMPT = "Reply with the single word OK."
# 영상·이미지 probe 와 같은 기준 영상·구간(0-7s, 1x 기준 462토큰).
DEFAULT_VIDEO = (
    "C:/Users/User/orca/ktc4-chonnam-2/src/daesingo/search/video/"
    "20260620_141628_EVT_1.avi"
)
DEFAULT_ENV = "C:/Users/User/orca/ktc4-chonnam-2/.env"

# (speed, 인코딩 fps(느려진 영상 기준), max_height)
CONDITIONS = [
    (1.0, 1.0, 360),
    (1.0, 4.0, 360),
    (0.5, 1.0, 360),
    (0.5, 4.0, 360),
    (0.5, 1.0, 720),
    (0.25, 1.0, 360),
    (0.25, 4.0, 360),
]


def _tool(name: str) -> str:
    p = shutil.which(name)
    if p is None:
        raise SystemExit(f"{name} not found on PATH")
    return p


def _encode(video: Path, start: float, end: float, speed: float, fps: float,
            max_height: int, dest: Path) -> None:
    """[start,end] 를 자르고 speed 배속으로 늘린 뒤 fps·downscale, 무음 H.264."""
    vf = f"setpts=PTS/{speed},fps={fps},scale=-2:'min({max_height},ih)'"
    # -t 는 -i 앞(입력 옵션)이어야 한다. 뒤에 두면 늘어난 출력이 원래 길이로 잘린다.
    args = [_tool("ffmpeg"), "-y", "-ss", str(start), "-t", str(end - start),
            "-i", str(video), "-vf", vf, "-c:v", "libx264", "-an",
            "-movflags", "+faststart", str(dest)]
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {r.stderr.decode(errors='replace')[-400:]}")


def _probe(path: Path) -> tuple[float, int]:
    """(duration_sec, frame_count)."""
    r = subprocess.run(
        [_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames:format=duration", "-of", "json", str(path)],
        capture_output=True, check=True,
    )
    info = json.loads(r.stdout)
    return float(info["format"]["duration"]), int(info["streams"][0]["nb_read_frames"])


@dataclass
class Row:
    label: str
    speed: float
    encode_fps: float
    max_height: int
    duration_sec: float
    frames: int
    file_bytes: int
    status: str
    prompt_tokens: int | None
    video_tokens: int | None


def _call(client, cfg: GeminiSearchConfig, content: list[dict]) -> tuple[str, int | None]:
    try:
        completion = client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": content}],
            reasoning_effort=cfg.reasoning_effort,
        )
    except Exception as exc:  # noqa: BLE001 — 수용 여부도 측정 대상이라 원문을 남긴다
        return (f"{type(exc).__name__}: {exc}"[:200], None)
    usage = getattr(completion, "usage", None)
    return ("200", getattr(usage, "prompt_tokens", None))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=DEFAULT_VIDEO)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=7.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--env", default=DEFAULT_ENV)
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    api_key = api_key_from_env(env)
    if not api_key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=api_key, max_retries=0
    )
    video = Path(args.video)
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")

    text = {"type": "text", "text": PROMPT}
    base_status, baseline = _call(client, cfg, [text])
    if baseline is None:
        raise SystemExit(f"baseline call failed: {base_status}")

    rows: list[Row] = []
    with tempfile.TemporaryDirectory(prefix="slow_probe_") as td:
        for speed, fps, mh in CONDITIONS:
            dest = Path(td) / f"s{speed}_f{fps}_{mh}.mp4"
            _encode(video, args.start, args.end, speed, fps, mh, dest)
            dur, frames = _probe(dest)
            data_url = "data:video/mp4;base64," + base64.b64encode(dest.read_bytes()).decode()
            status, pt = _call(client, cfg, [text, {"type": "file", "file": {"file_data": data_url}}])
            rows.append(Row(f"{speed}x/{fps}fps/{mh}p", speed, fps, mh, round(dur, 3), frames,
                            dest.stat().st_size, status, pt,
                            None if pt is None else pt - baseline))

    hdr = f"{'label':<20}{'dur':>8}{'frames':>8}{'bytes':>10}{'status':>8}{'ptok':>7}{'vtok':>7}{'vtok/66':>9}"
    print(f"text baseline tokens: {baseline}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        per = "" if r.video_tokens is None else f"{r.video_tokens / 66:.1f}"
        print(f"{r.label:<20}{r.duration_sec:>8}{r.frames:>8}{r.file_bytes:>10}"
              f"{r.status[:8]:>8}{str(r.prompt_tokens):>7}{str(r.video_tokens):>7}{per:>9}")

    if args.out:
        args.out.write_text(json.dumps(
            {"prompt": PROMPT, "model": cfg.model, "video": video.name,
             "interval": [args.start, args.end], "text_baseline_tokens": baseline,
             "rows": [asdict(r) for r in rows]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
