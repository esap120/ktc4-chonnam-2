"""Q3 confidence 실험 — 정정 발화에 무관한 사실을 끼워 넣으면 confidence가 low로 나오는가(멘토 피드백 2026-10-04 Q3).

후보 프롬프트 v1(`CANDIDATE_SYSTEM_PROMPT`)과 v2(`CANDIDATE_SYSTEM_PROMPT_V2`, 무관 사실 무시 · low 지시 추가)를
같은 케이스로 케이스마다 여러 번(기본 5회) 돌린다. 기존 결과는 1회짜리라 v1도 다시 반복한다.

    python scripts/confidence_experiment.py run --prompt v1 --repeats 5
    python scripts/confidence_experiment.py run --prompt v2 --repeats 5
    python scripts/confidence_experiment.py judge --prompt v1 --run-id <id>     # JUDGE_MODEL 환경변수
    python scripts/confidence_experiment.py judge --prompt v2 --run-id <id>
    python scripts/confidence_experiment.py summarize --judge-run-id <id>

환경변수는 `runner.py` · `judge.py`와 같다(`README.md`). 결과는 `predictions-q3/<prompt>/<model>/<case>.r<k>.json`이고
이미 있는 파일은 건너뛴다 — 중간에 끊겨도 같은 명령으로 이어서 돈다.
"""
from __future__ import annotations

import argparse
import collections
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from candidates import MODEL_IDS, CandidateAdapter, JudgeAdapter
from dataset import load_dataset
from schema import CANDIDATE_SYSTEM_PROMPT, CANDIDATE_SYSTEM_PROMPT_V2, CANDIDATE_SYSTEM_PROMPT_V3, FIELDS

PROMPTS = {"v1": CANDIDATE_SYSTEM_PROMPT, "v2": CANDIDATE_SYSTEM_PROMPT_V2, "v3": CANDIDATE_SYSTEM_PROMPT_V3}

# 케이스 묶음(id 접두어). 기대 confidence는 expected_notes 기준.
GROUPS = {
    "slip_in": ("case-15a", "case-15d"),  # 정정 + 무관한 다른 사건 끼워 넣기 → low, 무관 사실 무시
    "vague": ("case-15b", "case-15e"),  # 정정 + 모호한 추가 정정 → low
    "reset": ("case-15c",),  # 전면 취소 뒤 새 신고 → high
    "regression": ("case-17a", "case-17b", "case-17c", "case-16a", "case-16b"),  # 정상 · 새 사고 → high 유지
}
JUDGED_GROUPS = ("slip_in", "vague")  # 필드 정확도는 이 묶음만 judge로 판정한다


def _cases(dataset_path: Path) -> dict:
    by_id = {c.id: c for c in load_dataset(dataset_path)}
    picked = {}
    for group, prefixes in GROUPS.items():
        for prefix in prefixes:
            match = [cid for cid in by_id if cid.startswith(prefix + "-")]
            assert len(match) == 1, (prefix, match)
            picked[match[0]] = (group, by_id[match[0]])
    return picked


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> None:
    cases = _cases(Path(args.dataset))
    out = Path(args.out) / args.prompt

    def run_model(model_name: str) -> int:
        adapter = CandidateAdapter(model_name, system_prompt=PROMPTS[args.prompt])
        written = 0
        for case_id, (group, case) in cases.items():
            for k in range(1, args.repeats + 1):
                path = out / model_name / f"{case_id}.r{k}.json"
                if path.exists():
                    continue
                r = adapter.extract(case.input_sentence, case.prior_hints)
                _write(path, {"case_id": case_id, "group": group, "prompt": args.prompt, "repeat": k,
                              "model_name": model_name, "raw_text": r.raw_text, "parsed": r.parsed,
                              "latency_ms": r.latency_ms, "prompt_tokens": r.prompt_tokens,
                              "completion_tokens": r.completion_tokens, "cost_krw": r.cost_krw, "error": r.error})
                written += 1
                print(f"[{args.prompt}/{model_name}] {case_id} r{k} error={r.error is not None}", flush=True)
        return written

    models = args.models or list(MODEL_IDS)
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        total = sum(pool.map(run_model, models))
    print(f"{args.prompt}: {total}개 기록")


def cmd_judge(args: argparse.Namespace) -> None:
    import os

    cases = _cases(Path(args.dataset))
    judge = JudgeAdapter(os.environ["JUDGE_MODEL"])
    out = Path(args.out) / args.prompt
    written = 0
    for pred_path in sorted(out.glob("*/*.r*.json")):
        if ".judge." in pred_path.name:
            continue
        pred = json.loads(pred_path.read_text(encoding="utf-8"))
        if pred["group"] not in JUDGED_GROUPS or pred["error"]:
            continue
        path = pred_path.with_name(pred_path.name.replace(".json", f".judge.{args.run_id}.json"))
        if path.exists():
            continue
        case = cases[pred["case_id"]][1]
        for attempt in range(1, 4):  # Elice 경유 구조화 출력이 가끔 스키마를 어긴다(Opus 5에서 7%)
            r = judge.judge(case.input_sentence, case.prior_hints, case.expected_notes, pred["parsed"])
            if not r.error:
                break
        _write(path, {"run_id": args.run_id, "judge_model": judge.model_name, "attempts": attempt,
                      "case_id": pred["case_id"], "parsed": r.parsed, "prompt_tokens": r.prompt_tokens,
                      "completion_tokens": r.completion_tokens, "cost_krw": r.cost_krw, "error": r.error})
        written += 1
    print(f"{args.prompt}: judge {written}개 기록")


def cmd_summarize(args: argparse.Namespace) -> None:
    root = Path(args.out)
    preds = collections.defaultdict(list)  # (prompt, model, case) -> [parsed]
    judged = collections.defaultdict(list)  # (prompt, model, group) -> [verdict == correct]
    groups, errors = {}, collections.Counter()
    for path in sorted(root.glob("*/*/*.r*.json")):
        if ".judge." in path.name:
            continue
        p = json.loads(path.read_text(encoding="utf-8"))
        groups[p["case_id"]] = p["group"]
        if p["error"] or not p["parsed"]:
            errors[(p["prompt"], p["model_name"])] += 1
            continue
        preds[(p["prompt"], p["model_name"], p["case_id"])].append(p["parsed"])
        jpath = path.with_name(path.name.replace(".json", f".judge.{args.judge_run_id}.json"))
        if jpath.exists():
            j = json.loads(jpath.read_text(encoding="utf-8"))
            if j["parsed"]:
                judged[(p["prompt"], p["model_name"], p["group"])] += [j["parsed"][f]["verdict"] == "correct" for f in FIELDS]

    def low_rate(prompt: str, model: str, group: str) -> str:
        confs = [x["confidence"] for (pr, m, c), xs in preds.items() if pr == prompt and m == model and groups[c] == group for x in xs]
        return f"{sum(c == 'low' for c in confs)}/{len(confs)}" if confs else "-"

    def consistency(prompt: str, model: str) -> str:
        """케이스마다 반복 결과 중 가장 흔한 출력(6필드 전체)과 같은 비율의 평균."""
        rates = []
        for (pr, m, _), xs in preds.items():
            if pr == prompt and m == model and len(xs) > 1:
                keys = [json.dumps({f: x.get(f) for f in FIELDS}, ensure_ascii=False, sort_keys=True) for x in xs]
                rates.append(collections.Counter(keys).most_common(1)[0][1] / len(keys))
        return f"{sum(rates) / len(rates):.0%}" if rates else "-"

    prompts = sorted({k[0] for k in preds})
    models = sorted({k[1] for k in preds})
    print("confidence=low 비율 (반복 합계)  ·  필드 정확도(judge, slip_in+vague)  ·  반복 일관성(6필드 동일)")
    header = ["model", "prompt", *GROUPS, "field_acc", "consistency", "errors"]
    print("| " + " | ".join(header) + " |")
    print("|" + " --- |" * len(header))
    for model in models:
        for prompt in prompts:
            acc = [v for g in JUDGED_GROUPS for v in judged[(prompt, model, g)]]
            acc_s = f"{sum(acc) / len(acc):.0%}" if acc else "-"
            row = [model, prompt, *(low_rate(prompt, model, g) for g in GROUPS), acc_s, consistency(prompt, model), str(errors[(prompt, model)])]
            print("| " + " | ".join(row) + " |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, func in (("run", cmd_run), ("judge", cmd_judge), ("summarize", cmd_summarize)):
        s = sub.add_parser(name)
        s.add_argument("--dataset", default="datasets/intent-hint-robustness-v2.jsonl")
        s.add_argument("--out", default="predictions-q3")
        s.set_defaults(func=func)
        if name in ("run", "judge"):
            s.add_argument("--prompt", choices=sorted(PROMPTS), required=True)
        if name == "run":
            s.add_argument("--repeats", type=int, default=5)
            s.add_argument("--models", nargs="*", choices=sorted(MODEL_IDS), help="기본: 전체")
        if name == "judge":
            s.add_argument("--run-id", required=True)
        if name == "summarize":
            s.add_argument("--judge-run-id", required=True)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
