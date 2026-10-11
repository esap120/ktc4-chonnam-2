#!/usr/bin/env python
"""고정 구간 Fine 에 공간 crop 과 대상 힌트를 각각·함께 줄 때 판정이 바뀌는가.

gemini_fine_window_trace 의 후속이다. 프레임은 원본 해상도에서 뽑는다(crop 은 축소 전에
잘라야 원본 디테일이 남는다). 이미지 1장 토큰은 해상도와 무관하게 같으므로 조건 간 토큰은
같다. 프롬프트는 diagnostic-v1 Fine 이고 crop 조건만 fine-crop-v1 을 덧붙인다.
응답 원문이 들어가므로 --out 은 저장소 밖(.superpowers/)에 둔다. 실행(유료):
uv run --extra eval-gemini python scripts/gemini_fine_crop_hint_trace.py --out .superpowers/fine-window/<json>
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

from gemini_coarse_fine_slowdown_trace import _note
from gemini_fine_image_accuracy import DEFAULT_ENV, VID, _ffmpeg, _msg
from gemini_fine_window_trace import _origin_sec

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.diagnostic_prompts import (
    _compose,
    checklist_instruction,
    diagnostic_fine_prompt,
)
from daesingo.search.decision_trace import DiagnosticFineResponse
from daesingo.search.scope import VisualEventType

SOLID = VisualEventType.SOLID_LINE_LANE_CHANGE
CROP = "crop=iw/2:ih/2:iw/4:ih/4"  # 원본 가운데 1/2 — 소실점 부근의 먼 차량

# (clip, 시작, 끝, 기대, 힌트). 힌트는 운영 target_hint 자리에 들어간다.
CASES = [
    ("20260620_141927_EVT_1.avi", 4.0, 10.0, "OBSERVED", "앞쪽 멀리 보이는 회색 SUV"),        # 1080p
    ("YT_0003_C05.mp4", 10.0, 13.0, "OBSERVED", "오른쪽 차로의 검은색 승용차"),            # 360p 대조
    # 점선 변경 주체는 정답지에 없다. 화면에서 가장 뚜렷한 앞차를 힌트로 준다.
    ("20260620_141956_EVT_1.avi", 10.0, 14.0, "NOT_OBSERVED", "앞쪽 흰색 승용차"),          # 1080p
]
CONDITIONS = [  # (이름, crop, 힌트 사용)
    ("full", False, False),
    ("full+hint", False, True),
    ("crop", True, False),
    ("crop+hint", True, True),
]


def _extract(video: Path, start: float, end: float, fps: float, crop: bool, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    vf = f"fps={fps}" + (f",{CROP}" if crop else "")
    r = subprocess.run(
        [_ffmpeg(), "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
         "-vf", vf, "-qscale:v", "2", str(outdir / "f_%03d.jpg")],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return sorted(outdir.glob("f_*.jpg"))


def _slow_clip(video: Path, start: float, end: float, fps: float, crop: bool, dest: Path) -> Path:
    """fps 장/초로 뽑아 재생 1초 = 원본 프레임 1장이 되게 늘린다(프록시 1 fps 샘플링과 1:1)."""
    vf = f"fps={fps}" + (f",{CROP}" if crop else "") + f",setpts=PTS*{fps}"
    r = subprocess.run(
        [_ffmpeg(), "-y", "-ss", str(start), "-to", str(end), "-i", str(video),
         "-vf", vf, "-c:v", "libx264", "-an", "-movflags", "+faststart", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return dest


def _video_msg(prompt: str, clip: Path) -> list[dict]:
    url = "data:video/mp4;base64," + base64.b64encode(clip.read_bytes()).decode()
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "file", "file": {"file_data": url}},
    ]}]


def _rescale_offsets(payload: dict, factor: float) -> None:
    """느려진 영상 기준 at_offset_ms -> 원본 기준."""
    for key in ("temporal_facts", "decision_basis"):
        for item in payload.get(key, ()):
            if item.get("at_offset_ms") is not None:
                item["at_offset_ms"] = round(item["at_offset_ms"] * factor)


def _prompt(crop: bool, hint: str, start: float, end: float):
    template = diagnostic_fine_prompt(SOLID)
    if crop:
        template = _compose(template, "fine-crop-v1")
    return template, template.render(
        event_type=SOLID.value, target_hint=hint, start_sec=start, end_sec=end,
        criteria=checklist_instruction(SOLID),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--clips", nargs="+", default=None, help="clip 파일명 앞부분으로 거른다")
    ap.add_argument("--conditions", nargs="+", default=[c[0] for c in CONDITIONS])
    ap.add_argument("--transport", choices=["image", "video"], default="image",
                    help="video: 1/fps 배속으로 늘린 영상(프레임당 66토큰)")
    args = ap.parse_args()
    cases = [c for c in CASES if args.clips is None or c[0].startswith(tuple(args.clips))]
    conditions = [c for c in CONDITIONS if c[0] in args.conditions]

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=300.0
    )

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="crop_") as td:
        for i, (clip, start, end, expected, hint_text) in enumerate(cases):
            video = args.transport == "video"
            make = _slow_clip if video else _extract
            media = {crop: make(Path(VID) / clip, start, end, args.fps, crop,
                                Path(td) / (f"{i}_{crop}.mp4" if video else f"{i}_{crop}"))
                     for crop in (False, True)}
            for rep in range(1, args.repeat + 1):
                for name, crop, use_hint in conditions:
                    hint = hint_text if use_hint else "없음"
                    template, prompt = _prompt(crop, hint, start, end)
                    if video:
                        prompt += _note(1 / args.fps, False)
                    row = {"clip": clip, "window": [start, end], "expected": expected,
                           "condition": name, "hint": hint, "repeat": rep, "fps": args.fps,
                           "transport": args.transport,
                           "frames": round((end - start) * args.fps), "prompt_version": template.version,
                           "prompt_sha256": template.fingerprint}
                    t0 = time.monotonic()
                    try:
                        comp = client.chat.completions.parse(
                            model=cfg.model,
                            messages=(_video_msg(prompt, media[crop]) if video
                                      else _msg(prompt, media[crop])),
                            response_format=DiagnosticFineResponse,
                            reasoning_effort=cfg.reasoning_effort,
                        )
                        parsed = comp.choices[0].message.parsed
                        payload = parsed.model_dump(mode="json") if parsed else None
                        if payload and video:
                            _rescale_offsets(payload, 1 / args.fps)
                        row |= {
                            "verification": payload["verification"] if payload else "NO_PARSE",
                            "observed_at_origin_sec": _origin_sec(payload, start) if payload else [],
                            "uncertainty_count": len(payload["uncertainties"]) if payload else None,
                            "response": payload,
                            "input_tokens": getattr(comp.usage, "prompt_tokens", None),
                            "output_tokens": getattr(comp.usage, "completion_tokens", None),
                        }
                    except Exception as exc:  # noqa: BLE001 — 실패도 한 행으로 남긴다
                        row |= {"verification": f"FAILED:{type(exc).__name__}",
                                "error": str(exc)[:300]}
                    row["latency_sec"] = round(time.monotonic() - t0, 2)
                    row["correct"] = row["verification"] == expected
                    rows.append(row)
                    target = (row.get("response") or {}).get("target", {}).get("described_as")
                    print(f"  {name:<10} r{rep} {clip:<26} exp={expected:<12} "
                          f"got={row['verification']:<14} target={target}")
                    args.out.write_text(json.dumps(
                        {"model": cfg.model, "reasoning_effort": cfg.reasoning_effort,
                         "transport": args.transport, "crop": CROP, "fps": args.fps,
                         "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 조건 × 구간 (맞음/회차) ===")
    for name, _, _ in conditions:
        cells = []
        for clip, *_ in cases:
            sub = [r for r in rows if r["condition"] == name and r["clip"] == clip]
            cells.append(f"{clip[:14]} {sum(r['correct'] for r in sub)}/{len(sub)}")
        print(f"  {name:<10} " + " | ".join(cells))


if __name__ == "__main__":
    main()
