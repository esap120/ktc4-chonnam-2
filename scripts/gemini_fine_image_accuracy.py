#!/usr/bin/env python
"""이미지 프레임 전송 시 fps 를 올리면 Fine 판별 정확도가 오르는가.

gemini-image-frame-probe 는 토큰(정보량)까지만 봤다. 이건 정확도다: 실제
fine_prompt_for(SOLID_LINE_LANE_CHANGE) + FineResponse 구조화 출력으로 video/정답지.md
의 라벨 클립을 이미지로(fps 1/2/4) 넣어 OBSERVED/NOT_OBSERVED 를 정답과 대조한다.

해상도는 720p 고정(토큰은 360/720 동일이나 정확도엔 화질이 영향 줄 수 있어 보수적으로).
변수는 fps 뿐. 실행(유료): uv run --extra eval-gemini python scripts/gemini_fine_image_accuracy.py
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.prompts import fine_prompt_for
from daesingo.search.schemas import FineResponse
from daesingo.search.scope import VisualEventType

VID = "C:/Users/User/orca/ktc4-chonnam-2/src/daesingo/search/video"
DEFAULT_ENV = "C:/Users/User/orca/ktc4-chonnam-2/.env"
EVENT = VisualEventType.SOLID_LINE_LANE_CHANGE

# video/정답지.md 의 SOLID_LINE_LANE_CHANGE 라벨. (clip, start, end, 기대 verification)
# 무변경 클립은 모델이 과탐했던/그럴듯한 구간을 준다 — Fine 은 NOT_OBSERVED 여야 옳다.
CASES = [
    ("20260620_141927_EVT_1.avi", 4.0, 9.0, "OBSERVED"),      # 백색 실선 위반
    ("20260620_141956_EVT_1.avi", 10.0, 14.0, "NOT_OBSERVED"),  # 백색 점선(합법)
    ("20260620_141628_EVT_1.avi", 0.0, 7.0, "NOT_OBSERVED"),   # 무변경(모델 FP 이력)
    ("20260620_150504_EVT_1.avi", 0.0, 8.0, "NOT_OBSERVED"),   # 무변경
    ("youtube_clip_01.mp4", 0.0, 2.0, "OBSERVED"),             # 실선
    ("YT_0003_C05.mp4", 10.0, 13.0, "OBSERVED"),               # 실선
]
FPS_LIST = [1.0, 2.0, 4.0]


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p is None:
        raise SystemExit("ffmpeg not found")
    return p


def _extract(video: Path, start: float, end: float, fps: float, outdir: Path,
             height: int = 720) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    args = [
        _ffmpeg(), "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
        "-vf", f"fps={fps},scale=-2:'min({height},ih)'", "-qscale:v", "2",
        str(outdir / "f_%03d.jpg"),
    ]
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return sorted(outdir.glob("f_*.jpg"))


def _msg(prompt: str, frames: list[Path], detail: str | None = "high") -> list[dict]:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for f in frames:
        url = "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
        image = {"url": url} | ({"detail": detail} if detail else {})  # None = detail 생략(auto)
        content.append({"type": "image_url", "image_url": image})
    return [{"role": "user", "content": content}]


@dataclass
class Row:
    clip: str
    fps: float
    frames: int
    expected: str
    got: str            # verification 또는 에러
    correct: bool
    input_tokens: int | None
    output_tokens: int | None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")

    import importlib
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=180.0
    )

    rows: list[Row] = []
    with tempfile.TemporaryDirectory(prefix="acc_") as td:
        tmp = Path(td)
        for clip, start, end, expected in CASES:
            video = Path(VID) / clip
            if not video.is_file():
                rows.append(Row(clip, 0, 0, expected, "VIDEO_MISSING", False, None, None))
                continue
            dur = end - start
            prompt = fine_prompt_for(EVENT).render(
                event_type=EVENT.value, target_hint="없음",
                start_sec=0.0, end_sec=dur,
            )
            for fps in FPS_LIST:
                frames = _extract(video, start, end, fps, tmp / f"{clip}_{fps}")
                try:
                    comp = client.chat.completions.parse(
                        model=cfg.model, messages=_msg(prompt, frames),
                        response_format=FineResponse,
                        reasoning_effort=cfg.reasoning_effort,
                    )
                    parsed = comp.choices[0].message.parsed
                    got = parsed.verification.value if parsed else "NO_PARSE"
                    usage = getattr(comp, "usage", None)
                    it = getattr(usage, "prompt_tokens", None)
                    ot = getattr(usage, "completion_tokens", None)
                except Exception as exc:  # noqa: BLE001
                    got, it, ot = f"{type(exc).__name__}: {exc}"[:120], None, None
                rows.append(Row(clip, fps, len(frames), expected, got,
                                got == expected, it, ot))
                print(f"  {clip:<28} fps={fps} frames={len(frames):>2} "
                      f"exp={expected:<12} got={got:<14} {'OK' if got==expected else 'X'}")

    # 집계
    print("\n=== fps별 정확도 ===")
    for fps in FPS_LIST:
        sub = [r for r in rows if r.fps == fps and r.got not in ("VIDEO_MISSING",)]
        ok = sum(1 for r in sub if r.correct)
        print(f"  {fps}fps: {ok}/{len(sub)} correct")

    if args.out:
        args.out.write_text(
            json.dumps({"event": EVENT.value, "resolution": "720p",
                        "fps_list": FPS_LIST, "rows": [asdict(r) for r in rows]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
