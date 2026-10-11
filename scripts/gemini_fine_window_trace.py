#!/usr/bin/env python
"""정답을 아는 고정 구간에 Fine 만 돌려 profile 별 판정과 근거를 남긴다.

Coarse 흔들림을 빼고 Fine 만 본다. 프롬프트·응답 스키마는 진단 실행기의 `_fine_spec`
그대로이고, 전송은 gemini_fine_image_accuracy 와 같은 이미지 프레임(720p)이다.
응답 전체(primitives·uncertainties·decision_basis)와 at_offset_ms 의 원본 초 환산을
저장한다. 응답 원문이 들어가므로 --out 은 저장소 밖(.superpowers/)에 둔다. 실행(유료):
uv run --extra eval-gemini python scripts/gemini_fine_window_trace.py --out .superpowers/fine-window/<json>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import tempfile
import time
from pathlib import Path

from gemini_fine_image_accuracy import DEFAULT_ENV, VID, _extract, _msg

from daesingo.common import load_env_file
from daesingo.search.config import GeminiSearchConfig, api_key_from_env
from daesingo.search.diagnostic_call import FineInput, _fine_spec
from daesingo.search.diagnostic_models import DiagnosticProfile
from daesingo.search.media import PreparedMedia
from daesingo.search.schemas import CoarseCandidate
from daesingo.search.scope import VisualEventType

SOLID = VisualEventType.SOLID_LINE_LANE_CHANGE
CENTER = VisualEventType.CENTER_LINE_CROSSING

# (clip, 사건, 시작, 끝, 기대 verification) — video/정답지.md. padding 없이 정답·음성 구간만.
CASES = [
    ("20260620_141927_EVT_1.avi", SOLID, 4.0, 10.0, "OBSERVED"),       # 앞 SUV 백색 실선
    ("youtube_clip_01.mp4", SOLID, 0.0, 2.0, "OBSERVED"),
    ("YT_0003_C05.mp4", SOLID, 10.0, 13.0, "OBSERVED"),
    ("YT_0002_C00.mp4", CENTER, 11.0, 14.0, "OBSERVED"),
    ("YT_0003_C05.mp4", SOLID, 3.0, 8.0, "NOT_OBSERVED"),         # 정상 주행(Coarse 오탐 구간)
    ("20260620_141956_EVT_1.avi", SOLID, 10.0, 14.0, "NOT_OBSERVED"),  # 백색 점선(합법)
    ("20260620_141628_EVT_1.avi", SOLID, 0.0, 7.0, "NOT_OBSERVED"),    # 무변경
    ("20260620_150504_EVT_1.avi", SOLID, 0.0, 8.0, "NOT_OBSERVED"),    # 무변경
]


def _probe(event: VisualEventType, start: float, end: float) -> FineInput:
    # _fine_spec 은 candidate 에서 사건 유형만, prepared 에서 원본 범위만 읽는다.
    candidate = CoarseCandidate.model_validate({
        "event_type": event, "span": {"start_sec": start, "end_sec": end},
        "at_sec": start, "observed": (), "score": 0.5,
    })
    prepared = PreparedMedia(Path("frames"), "image/jpeg", 0, end - start, start, end)
    return FineInput(candidate, 0, prepared)


def _origin_sec(payload: dict, start: float) -> list[float]:
    offsets = [f.get("at_offset_ms") for f in payload.get("temporal_facts", ())]
    offsets += [b.get("at_offset_ms") for b in payload.get("decision_basis", ())]
    return sorted({round(start + o / 1000, 2) for o in offsets if o is not None})


def _fewshot_parts(spec: dict) -> list[dict]:
    """--fewshot JSON 의 참고 예시를 검증 대상 프레임 앞에 넣을 content 조각으로 만든다."""
    parts: list[dict] = [{"type": "text", "text": spec["intro"]}]
    for ex in spec["examples"]:
        url = "data:image/jpeg;base64," + base64.b64encode(Path(ex["image"]).read_bytes()).decode()
        parts += [{"type": "text", "text": ex["text"]},
                  {"type": "image_url", "image_url": {"url": url, "detail": "high"}}]
    return parts + [{"type": "text", "text": spec["outro"]}]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=DEFAULT_ENV)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--profiles", nargs="+", default=["diagnostic-v1", "diagnostic-uncertain-v1"])
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--reasoning", nargs="+", default=None,
                    help="비교할 reasoning_effort 값들. 없으면 설정값 하나")
    ap.add_argument("--transport", choices=["image", "video"], default="image",
                    help="video: 1/fps 배속으로 늘린 영상(운영 v3 전송)")
    ap.add_argument("--height", type=int, default=720, help="이미지 프레임 최대 높이(운영 MediaPreparer 는 360)")
    ap.add_argument("--detail", choices=["high", "low", "auto"], default="high",
                    help="image_url detail. auto 는 값을 보내지 않는다(파이프라인 ImageInvoker 와 같음)")
    ap.add_argument("--pad", type=float, default=0.0,
                    help="구간 앞뒤 확장 초(운영 fine_padding_sec=4 재현용). 시작은 0 아래로 내려가지 않는다")
    ap.add_argument("--fewshot", type=Path, default=None,
                    help="참고 예시 JSON(intro·examples[image,text]·outro·events). 예시 이미지는 저장소 밖에 둔다")
    args = ap.parse_args()
    fewshot = json.loads(args.fewshot.read_text(encoding="utf-8")) if args.fewshot else None
    fewshot_parts = _fewshot_parts(fewshot) if fewshot else []
    fewshot_sha = (hashlib.sha256(json.dumps(fewshot_parts, sort_keys=True).encode()).hexdigest()
                   if fewshot else None)
    video = args.transport == "video"
    if video:  # crop_hint 가 이 모듈을 import 하므로 순환을 피해 여기서 가져온다
        from gemini_coarse_fine_slowdown_trace import _note
        from gemini_fine_crop_hint_trace import _rescale_offsets, _slow_clip, _video_msg

    env = load_env_file(args.env)
    cfg = GeminiSearchConfig.from_dotenv(env)
    key = api_key_from_env(env)
    if not key:
        raise SystemExit(f"no ELICE_ML_API_KEY in {args.env}")
    client = importlib.import_module("openai").OpenAI(
        base_url=cfg.base_url, api_key=key, max_retries=0, timeout=300.0
    )
    profiles = [DiagnosticProfile(p) for p in args.profiles]
    efforts = args.reasoning or [cfg.reasoning_effort]
    arms = [(e, p) for e in efforts for p in profiles]

    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="win_") as td:
        for i, (clip, event, start, end, expected) in enumerate(CASES):
            start, end = max(0.0, start - args.pad), end + args.pad
            if video:
                media = _slow_clip(Path(VID) / clip, start, end, args.fps, False,
                                   Path(td) / f"{i}.mp4")
                n_frames = round((end - start) * args.fps)
            else:
                media = _extract(Path(VID) / clip, start, end, args.fps, Path(td) / str(i), args.height)
                end = min(end, start + len(media) / args.fps)  # 클립 끝을 넘은 pad 를 실제 길이로
                n_frames = len(media)
            for rep in range(1, args.repeat + 1):
                for effort, profile in arms:
                    spec = _fine_spec(_probe(event, start, end), profile)
                    prompt = spec.prompt + (_note(1 / args.fps, False) if video else "")
                    row = {"clip": clip, "event": event.value, "window": [start, end],
                           "expected": expected, "profile": profile.value, "repeat": rep,
                           "reasoning_effort": effort, "transport": args.transport,
                           "fps": args.fps, "frames": n_frames, "height": args.height,
                           "detail": args.detail, "pad": args.pad,
                           "prompt_version": spec.template.version,
                           "prompt_sha256": spec.template.fingerprint}
                    use_fewshot = bool(fewshot) and event.value in fewshot["events"]
                    row |= {"fewshot": fewshot["name"] if use_fewshot else None,
                            "fewshot_sha256": fewshot_sha if use_fewshot else None}
                    detail = None if args.detail == "auto" else args.detail
                    messages = _video_msg(prompt, media) if video else _msg(prompt, media, detail)
                    if use_fewshot:  # 지시문 바로 뒤, 검증 대상 프레임 앞
                        messages[0]["content"][1:1] = fewshot_parts
                    t0 = time.monotonic()
                    try:
                        comp = client.chat.completions.parse(
                            model=cfg.model,
                            messages=messages,
                            response_format=spec.response_model,
                            reasoning_effort=effort,
                        )
                        parsed = comp.choices[0].message.parsed
                        payload = parsed.model_dump(mode="json") if parsed else None
                        if payload and video:
                            _rescale_offsets(payload, 1 / args.fps)
                        usage = comp.usage
                        row |= {
                            "verification": payload["verification"] if payload else "NO_PARSE",
                            "observed_at_origin_sec": _origin_sec(payload, start) if payload else [],
                            "uncertainty_count": len(payload["uncertainties"]) if payload else None,
                            "response": payload,
                            "input_tokens": getattr(usage, "prompt_tokens", None),
                            "output_tokens": getattr(usage, "completion_tokens", None),
                        }
                    except Exception as exc:  # noqa: BLE001 — 실패도 한 행으로 남긴다
                        row |= {"verification": f"FAILED:{type(exc).__name__}",
                                "error": str(exc)[:300]}
                    row["latency_sec"] = round(time.monotonic() - t0, 2)
                    row["correct"] = row["verification"] == expected
                    rows.append(row)
                    print(f"  {effort:<6} {profile.value:<24} r{rep} {clip:<26} {start:>4}-{end:<4} "
                          f"exp={expected:<12} got={row['verification']:<14} "
                          f"unc={row.get('uncertainty_count')} out={row.get('output_tokens')} "
                          f"{row['latency_sec']}s")
                    # 조건마다 저장해 중간에 끊겨도 남긴다
                    args.out.write_text(json.dumps(
                        {"model": cfg.model, "reasoning_efforts": efforts,
                         "transport": args.transport, "fps": args.fps,
                         "fewshot": fewshot["name"] if fewshot else None, "rows": rows},
                        ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== reasoning × profile 별 ===")
    for effort, profile in arms:
        sub = [r for r in rows
               if r["profile"] == profile.value and r["reasoning_effort"] == effort]
        out = [r["output_tokens"] for r in sub if r.get("output_tokens") is not None]
        lat = [r["latency_sec"] for r in sub]
        pos = [r for r in sub if r["expected"] == "OBSERVED"]
        neg = [r for r in sub if r["expected"] == "NOT_OBSERVED"]
        dist: dict[str, int] = {}
        for r in sub:
            dist[r["verification"]] = dist.get(r["verification"], 0) + 1
        print(f"  {effort}/{profile.value}: 양성 {sum(r['correct'] for r in pos)}/{len(pos)}, "
              f"음성 {sum(r['correct'] for r in neg)}/{len(neg)}, "
              f"불확실성 기록 {sum(1 for r in sub if r.get('uncertainty_count'))}/{len(sub)}, "
              f"분포 {dist}, 평균 출력토큰 {sum(out) // max(len(out), 1)}, "
              f"평균 지연 {sum(lat) / max(len(lat), 1):.1f}s")


if __name__ == "__main__":
    main()
