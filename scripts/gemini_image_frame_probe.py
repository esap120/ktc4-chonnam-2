#!/usr/bin/env python
"""프레임을 이미지(image_url)로 보낼 때 fps/해상도가 모델에 전달되는가.

gemini-proxy-video-sampling-2026-09-28 실험의 이미지판. 방법은 같다: 고정 프롬프트
"Reply with the single word OK." 를 이미지 0장으로 보낸 입력 토큰(텍스트 baseline)을
빼서 이미지 토큰으로 본다. 클라이언트·base_url·model 은 운영 경로와 같게
GeminiSearchConfig.from_dotenv / .env ELICE_ML_API_KEY(기존 GEMINI_API_KEY도 읽음)를 쓴다.

측정:
  ⓐ 프록시가 image_url 을 수용하는가          -> 200 이면 수용
  ⓑ detail(low/high) 이 토큰을 바꾸는가        -> 바뀌면 해상도 등급이 실제 전달됨
  ⓒ 이미지 장당 토큰                            -> (총 - 텍스트 baseline) / 장수
  ⓓ 18 MiB 요청 상한 내 최대 장수              -> serialized bytes 로 확인

실행(유료 호출): uv run python scripts/gemini_image_frame_probe.py
결과는 stdout 표 + --out 지정 시 JSON. 영상/키는 저장하지 않는다.
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

PROMPT = "Reply with the single word OK."
# fps 실험과 같은 기준 영상·구간(0-7s). 이 파일은 신규 video/ 폴더엔 없고
# 기존 src/daesingo/search/video/ 에만 있다(fps baseline 462토큰과 비교하려면 필요).
DEFAULT_VIDEO = (
    "C:/Users/User/orca/ktc4-chonnam-2/src/daesingo/search/video/"
    "20260620_141628_EVT_1.avi"
)
# .env(ELICE_ML_API_KEY)는 main 작업트리에만 있다. worktree엔 없으므로 기본값으로 가리킨다.
DEFAULT_ENV = "C:/Users/User/orca/ktc4-chonnam-2/.env"


def _ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if p is None:
        raise SystemExit("ffmpeg not found on PATH")
    return p


def _extract_frames(
    video: Path, start: float, end: float, fps: float, max_height: int | None, outdir: Path
) -> list[Path]:
    """[start,end] 에서 fps 로 프레임 추출. max_height=None 이면 원본 해상도."""
    outdir.mkdir(parents=True, exist_ok=True)
    vf = f"fps={fps}"
    if max_height is not None:
        # media.py 와 같은 downscale-only 필터
        vf += f",scale=-2:'min({max_height},ih)'"
    args = [
        _ffmpeg(), "-y", "-ss", str(start), "-to", str(end),
        "-i", str(video), "-vf", vf, "-qscale:v", "2",
        str(outdir / "f_%03d.jpg"),
    ]
    r = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg failed: {r.stderr.decode(errors='replace')[-400:]}")
    return sorted(outdir.glob("f_*.jpg"))


def _data_url(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _image_message(frames: list[Path], detail: str | None) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": PROMPT}]
    for f in frames:
        img: dict = {"url": _data_url(f)}
        if detail is not None:
            img["detail"] = detail
        content.append({"type": "image_url", "image_url": img})
    return [{"role": "user", "content": content}]


def _serialized_bytes(cfg: GeminiSearchConfig, messages: list[dict]) -> int:
    return len(
        json.dumps(
            {"model": cfg.model, "messages": messages,
             "reasoning_effort": cfg.reasoning_effort},
            separators=(",", ":"),
        ).encode()
    )


@dataclass
class Row:
    label: str
    frames: int
    max_height: int | None
    detail: str | None
    request_bytes: int
    status: str            # "200" 또는 에러 원문
    prompt_tokens: int | None
    image_tokens: int | None  # prompt_tokens - text_baseline


def _call(client, cfg: GeminiSearchConfig, messages: list[dict]) -> tuple[str, int | None]:
    """(status, prompt_tokens) 반환. 에러면 status=원문, tokens=None."""
    try:
        completion = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            reasoning_effort=cfg.reasoning_effort,
        )
    except Exception as exc:  # noqa: BLE001 — 수용 여부(ⓐ)가 측정 대상이라 원문을 남긴다
        return (f"{type(exc).__name__}: {exc}"[:200], None)
    usage = getattr(completion, "usage", None)
    return ("200", getattr(usage, "prompt_tokens", None))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=DEFAULT_VIDEO)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=7.0)
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 경로")
    ap.add_argument("--env", default=DEFAULT_ENV, help=".env 경로(ELICE_ML_API_KEY)")
    args = ap.parse_args()

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    api_key = api_key_from_env(env)
    if not api_key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")

    import importlib
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=api_key, max_retries=0
    )
    video = Path(args.video)
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")

    rows: list[Row] = []

    # 텍스트 baseline (이미지 0장) — 차감 기준
    base_msg = [{"role": "user", "content": [{"type": "text", "text": PROMPT}]}]
    base_status, text_baseline = _call(client, cfg, base_msg)
    rows.append(Row("text-only(baseline)", 0, None, None,
                    _serialized_bytes(cfg, base_msg), base_status, text_baseline, 0))

    def run(label, frames, mh, detail):
        msgs = _image_message(frames, detail)
        rb = _serialized_bytes(cfg, msgs)
        status, pt = _call(client, cfg, msgs)
        img_tok = (pt - text_baseline) if (pt is not None and text_baseline is not None) else None
        rows.append(Row(label, len(frames), mh, detail, rb, status, pt, img_tok))

    with tempfile.TemporaryDirectory(prefix="img_probe_") as td:
        tmp = Path(td)

        # 실험 1: 1장 고정, detail·해상도 변화 (ⓑ,ⓒ)
        one_720 = _extract_frames(video, args.start, args.start + 1, 1.0, 720, tmp / "a")
        one_360 = _extract_frames(video, args.start, args.start + 1, 1.0, 360, tmp / "b")
        one_nat = _extract_frames(video, args.start, args.start + 1, 1.0, None, tmp / "c")
        run("1f/720p/detail=low", one_720[:1], 720, "low")
        run("1f/720p/detail=high", one_720[:1], 720, "high")
        run("1f/720p/detail=omit", one_720[:1], 720, None)
        run("1f/360p/detail=high", one_360[:1], 360, "high")
        run("1f/native/detail=high", one_nat[:1], None, "high")

        # 실험 2: 장수 증가 → 토큰 선형성·요청 상한 (ⓒ,ⓓ)
        for n_fps in (1.0, 2.0, 4.0):
            frames = _extract_frames(video, args.start, args.end, n_fps, 720, tmp / f"n{n_fps}")
            run(f"{int((args.end-args.start))}s@{n_fps}fps/720p/detail=high",
                frames, 720, "high")

    # 출력
    hdr = f"{'label':<34}{'imgs':>5}{'h':>6}{'detail':>8}{'req_bytes':>12}{'status':>8}{'ptok':>7}{'img_tok':>9}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r.label:<34}{r.frames:>5}{str(r.max_height):>6}{str(r.detail):>8}"
              f"{r.request_bytes:>12}{r.status[:8]:>8}{str(r.prompt_tokens):>7}{str(r.image_tokens):>9}")

    if args.out:
        args.out.write_text(
            json.dumps({"prompt": PROMPT, "video": video.name,
                        "interval": [args.start, args.end],
                        "rows": [asdict(r) for r in rows]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nsaved: {args.out}")


if __name__ == "__main__":
    main()
