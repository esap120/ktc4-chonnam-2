#!/usr/bin/env python
"""Coarse 만 돌려 정답 구간과 겹치는 후보를 내는지(recall)와 잘못된 후보 수를 잰다.

Fine 은 호출하지 않는다. 전송은 느린 영상 트레이스의 Coarse 조건과 같다: 360p·원본 2 fps 를
0.5x 로 늘려 재생 1초 = 원본 프레임 1장(프록시 1 fps 샘플링과 1:1), 안내 단락 동일.
프롬프트는 coarse-p3 와, 그 뒤에 delta 한 단락을 붙인 변형이다(한 변형에 변경 하나).
응답 원문이 들어가므로 --out 은 저장소 밖(.superpowers/)에 둔다. 실행(유료):
uv run --extra eval-gemini python scripts/gemini_coarse_recall_trace.py --out .superpowers/coarse-recall/<json>
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from gemini_coarse_fine_slowdown_trace import CASES, DEFAULT_ENV, VID, _ffmpeg, _note, _overlaps
from gemini_fine_crop_hint_trace import _video_msg

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.diagnostic_prompts import _compose
from daesingo.search.prompts import COARSE_PROMPT
from daesingo.search.schemas import CoarseResponse

SPEED = 0.5  # 원본 2 fps. --speed 0.25 = 원본 4 fps
PROFILES = {"coarse-p3": None, "coarse-subject-v1": "coarse-subject-v1",
            "coarse-multi-v1": "coarse-multi-v1"}
# YT_0003 은 0–10초가 정상 주행(사용자 확인). 그 구간 후보를 오탐으로 따로 센다.
NORMAL_WINDOWS = {"YT_0003_C05": (0.0, 10.0)}


def _slow_coarse(video: Path, dest: Path) -> Path:
    fps = 1 / SPEED
    r = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(video), "-an",
         "-vf", f"fps={fps},scale=-2:'min(360,ih)',setpts=PTS*{fps}",
         "-c:v", "libx264", "-movflags", "+faststart", str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg: {r.stderr.decode(errors='replace')[-300:]}")
    return dest


def main() -> None:
    global SPEED
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--profiles", nargs="+", default=list(PROFILES))
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--speed", type=float, default=SPEED)
    args = ap.parse_args()
    SPEED = args.speed

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=300.0
    )

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="coarse_") as td:
        media = {cid: _slow_coarse(Path(VID) / fname, Path(td) / f"{cid}.mp4")
                 for cid, fname, *_ in CASES}
        for rep in range(1, args.repeat + 1):
            for cid, _fname, dur, event, expected, truth in CASES:
                for profile in args.profiles:
                    template = COARSE_PROMPT
                    if PROFILES[profile]:
                        template = _compose(template, PROFILES[profile])
                    prompt = template.render(event_types=event, duration_sec=dur) + _note(SPEED, False)
                    row = {"case_id": cid, "event": event, "expected": expected, "truth": truth,
                           "profile": profile, "repeat": rep, "prompt_version": template.version,
                           "prompt_sha256": template.fingerprint}
                    t0 = time.monotonic()
                    try:
                        comp = client.chat.completions.parse(
                            model=cfg.model, messages=_video_msg(prompt, media[cid]),
                            response_format=CoarseResponse,
                            reasoning_effort=cfg.reasoning_effort,
                        )
                        parsed = comp.choices[0].message.parsed
                        cands = []
                        for c in (parsed.candidates if parsed else ()):
                            span = (round(c.span.start_sec * SPEED, 2), round(c.span.end_sec * SPEED, 2))
                            cands.append({"span": span, "at_sec": round(c.at_sec * SPEED, 2),
                                          "score": c.score, "hits_truth": _overlaps(span, truth),
                                          "observed": list(c.observed)})
                        normal = NORMAL_WINDOWS.get(cid)
                        row |= {
                            "status": "OK" if parsed else "NO_PARSE",
                            "candidates": cands,
                            "hit": any(c["hits_truth"] for c in cands),
                            "false_candidates": sum(not c["hits_truth"] for c in cands),
                            "normal_window_candidates": sum(_overlaps(c["span"], normal) for c in cands),
                            "input_tokens": getattr(comp.usage, "prompt_tokens", None),
                            "output_tokens": getattr(comp.usage, "completion_tokens", None),
                        }
                    except Exception as exc:  # noqa: BLE001 — 실패도 한 행으로 남긴다
                        row |= {"status": f"FAILED:{type(exc).__name__}", "error": str(exc)[:300],
                                "candidates": [], "hit": False, "false_candidates": None}
                    row["latency_sec"] = round(time.monotonic() - t0, 2)
                    rows.append(row)
                    print(f"  {profile:<18} r{rep} {cid:<22} truth={truth} "
                          f"cands={[c['span'] for c in row['candidates']]} hit={row['hit']}")
                    args.out.write_text(json.dumps(
                        {"model": cfg.model, "reasoning_effort": cfg.reasoning_effort,
                         "transport": f"video-360p-{SPEED}x", "rows": rows},
                        ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== profile 별 ===")
    for profile in args.profiles:
        sub = [r for r in rows if r["profile"] == profile]
        pos = [r for r in sub if r["expected"] == "OBSERVED"]
        neg = [r for r in sub if r["expected"] == "NOT_OBSERVED"]
        print(f"  {profile}: 위반 후보 적중 {sum(r['hit'] for r in pos)}/{len(pos)}, "
              f"위반 없는 클립 후보 {sum(len(r['candidates']) for r in neg)}, "
              f"정답 밖 후보 {sum(r['false_candidates'] or 0 for r in sub)}, "
              f"YT_0003 0–10초 후보 {sum(r.get('normal_window_candidates') or 0 for r in sub)}")
        for cid, *_ in CASES:
            c = [r for r in sub if r["case_id"] == cid]
            print(f"    {cid:<22} 적중 {sum(r['hit'] for r in c)}/{len(c)} "
                  f"후보수 {[len(r['candidates']) for r in c]}")


if __name__ == "__main__":
    main()
