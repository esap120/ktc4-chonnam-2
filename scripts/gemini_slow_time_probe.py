#!/usr/bin/env python
"""느린 영상에서 모델이 시각을 어느 기준(늘린 영상·원본)으로, 얼마나 정확히 답하는가.

Coarse 트레이스와 같은 영상(360p, 원본 2 fps 를 0.5x 로 늘림)과 대조 1x(1 fps)에
원본 기준 정해진 시각에 빨간 사각형을 그려 넣고, 사각형이 보이는 구간을 묻는다.
안내 단락은 Coarse 트레이스와 같다(_note). 원시 응답 시각과 그 원본 환산을 함께 남긴다.
실행(유료): uv run --extra eval-gemini python scripts/gemini_slow_time_probe.py --out <json>
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import tempfile
from pathlib import Path

from gemini_coarse_fine_slowdown_trace import DEFAULT_ENV, VID, _ffmpeg, _note
from gemini_fine_crop_hint_trace import _video_msg
from pydantic import BaseModel

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env

# (clip, 길이, 원본 기준 사각형 구간들)
CASES = [
    ("20260620_141927_EVT_1.avi", 20.025, [(6.0, 7.0), (15.0, 16.0)]),
    ("YT_0003_C05.mp4", 60.0, [(11.0, 12.0), (42.0, 43.0)]),
]
SPEEDS = [1.0, 0.5]


class Appearance(BaseModel):
    start_sec: float
    end_sec: float


class MarkerResponse(BaseModel):
    appearances: list[Appearance]


def _marked(video: Path, speed: float, marks: list[tuple[float, float]], dest: Path) -> Path:
    fps = 1 / speed
    # drawbox 의 t 는 setpts 전이라 원본 시각이다.
    boxes = ",".join(
        f"drawbox=x=iw*0.4:y=ih*0.1:w=iw*0.2:h=ih*0.2:color=red:t=fill:enable='between(t,{a},{b})'"
        for a, b in marks
    )
    vf = f"fps={fps},scale=-2:'min(360,ih)',{boxes},setpts=PTS*{fps}"
    r = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(video), "-an", "-vf", vf,
         "-c:v", "libx264", "-movflags", "+faststart", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return dest


def _prompt(duration: float, speed: float) -> str:
    text = (
        f"클립 길이: {duration:.3f}초\n"
        "화면 위쪽 가운데에 빨간 사각형이 나타나는 구간을 모두 찾아 start_sec, end_sec로 답하세요. "
        "시간은 클립 시작 기준 초입니다."
    )
    return text + (_note(speed, False) if speed != 1.0 else "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=300.0
    )

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="tprobe_") as td:
        for i, (clip, dur, marks) in enumerate(CASES):
            for speed in SPEEDS:
                media = _marked(Path(VID) / clip, speed, marks, Path(td) / f"{i}_{speed}.mp4")
                for rep in range(1, args.repeat + 1):
                    row = {"clip": clip, "speed": speed, "repeat": rep, "marks_origin": marks,
                           "marks_provided": [(a / speed, b / speed) for a, b in marks]}
                    try:
                        comp = client.chat.completions.parse(
                            model=cfg.model, messages=_video_msg(_prompt(dur, speed), media),
                            response_format=MarkerResponse,
                            reasoning_effort=cfg.reasoning_effort,
                        )
                        parsed = comp.choices[0].message.parsed
                        raw = [(a.start_sec, a.end_sec) for a in parsed.appearances] if parsed else []
                        row |= {"raw": raw,
                                "as_origin": [(round(a * speed, 2), round(b * speed, 2)) for a, b in raw],
                                "input_tokens": getattr(comp.usage, "prompt_tokens", None),
                                "output_tokens": getattr(comp.usage, "completion_tokens", None)}
                    except Exception as exc:  # noqa: BLE001 — 실패도 한 행으로 남긴다
                        row |= {"error": f"{type(exc).__name__}: {exc}"[:300]}
                    rows.append(row)
                    print(f"  {clip:<26} speed={speed} r{rep} provided={row['marks_provided']} "
                          f"raw={row.get('raw')} -> origin={row.get('as_origin')} (truth {marks})")
                    args.out.write_text(json.dumps({"model": cfg.model, "rows": rows},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
