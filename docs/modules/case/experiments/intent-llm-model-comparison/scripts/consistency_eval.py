"""robustness-v3 반복 일관성 평가 — 멘토 피드백 Q2(데이터 증강 · 반복 일관성) · #213(정확도 + 일관성 → 단일 점수).

    python scripts/consistency_eval.py run --models gemini-3.8-flash gemini-3.1-flash-lite   # 후보 호출(Elice)
    python scripts/consistency_eval.py rule-score                                           # 규칙 채점(호출 없음)
    python scripts/consistency_eval.py judge --run-id <id>                                   # 규칙으로 못 정한 것만 judge(JUDGE_MODEL)
    python scripts/consistency_eval.py summarize --judge-run-id <id>                         # 표 출력
    python scripts/consistency_eval.py run --models gpt-6-luna@none gemini-3.8-flash@low --sample 10 --repeats 1 --out predictions-luna/smoke
        # `model@effort`는 reasoning_effort 지정(#281), `--sample n`은 카테고리별로 고르게 n케이스만(smoke)

비용을 줄이려고 채점을 둘로 나눈다(`results/consistency-robustness-v3.md` §비용).

- **규칙 채점** — 데이터셋 `expected`(구조화 정답)로 판정한다. `correction_target` · `confidence`는 값 비교,
  4개 hint는 null/`null_or_vague`/`any_of`/`none_of`/`none_of_all_hints`로 판정한다. 비교 전에 소문자 · 공백 ·
  문장부호를 지운다.
- **judge** — 규칙으로 정하지 못한 필드(`unresolved`)가 있는 출력만, 같은 케이스에서 출력이 같으면 한 번만 보낸다.
  판정은 그 필드에만 쓰고 나머지는 규칙 판정을 쓴다.

일관성은 judge 없이 출력끼리 비교한다(정규화한 값이 같은가). 결과 파일은 `predictions-v3-consistency/<model>/<case>.r<k>.json`.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pricing import estimate_cost_krw
from schema import CANDIDATE_SYSTEM_PROMPT_V3, FIELDS

HINTS = ("time_hint", "vehicle_hint", "situation_hint", "location_hint")
DEFAULT_DATASET = "datasets/intent-hint-robustness-v3.jsonl"
DEFAULT_OUT = "predictions-v3-consistency"
HALLUCINATION_GATE = 0.05  # intent-llm-eval-target-thresholds.md §1 — 통과 조건


def normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[\W_]+", "", str(value).lower())


def load_cases(path: Path) -> dict[str, dict]:
    cases = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["id"] in cases:
                raise ValueError(f"중복 id: {row['id']}")
            cases[row["id"]] = row
    return cases


def _contains_any(value: str, words: list[str]) -> bool:
    return any(normalize(w) and normalize(w) in value for w in words)


def rule_verdicts(expected: dict, parsed: dict | None) -> dict[str, str]:
    """필드별 `correct` · `hallucinated` · `missed` · `wrong`(confidence 불일치) · `unresolved`(judge로)."""
    if parsed is None:
        return {f: "missed" for f in FIELDS}
    banned = expected.get("none_of_all_hints") or []
    out: dict[str, str] = {}
    for field in HINTS:
        exp, raw = expected[field], parsed.get(field)
        value = normalize(raw)
        if value == "":
            value = None
        if value is not None and _contains_any(value, banned):
            out[field] = "hallucinated"
        elif exp is None:
            out[field] = "correct" if value is None else "hallucinated"
        elif exp.get("null_or_vague"):
            out[field] = "correct" if value is None else "unresolved"
        elif value is None:
            out[field] = "missed"
        elif _contains_any(value, exp.get("none_of") or []):
            out[field] = "hallucinated"
        elif _contains_any(value, exp["any_of"]):
            out[field] = "correct"
        else:
            out[field] = "unresolved"
    if expected.get("events"):
        _apply_events(expected["events"], parsed, out)
    exp_ct, got_ct = expected["correction_target"], parsed.get("correction_target")
    if exp_ct == got_ct:
        out["correction_target"] = "correct"
    elif got_ct is None:
        out["correction_target"] = "missed"
    else:
        out["correction_target"] = "hallucinated"
    out["confidence"] = "correct" if parsed.get("confidence") == expected["confidence"] else "wrong"
    return out


def _apply_events(events: list[dict], parsed: dict, out: dict[str, str]) -> None:
    """여러 사건이 섞인 발화 — 출력한 필드들이 **한 사건**에 속해야 한다(사건 교차 조합은 오답).

    필드별 합집합 `any_of`로 먼저 판정한 결과(`out`)를 사건 단위로 다시 본다. 값이 있는 필드마다 맞는 사건 집합을
    구하고, 그 교집합이 비면 사건을 섞은 것이라 맞은 필드를 모두 `hallucinated`로 바꾼다. 교집합이 있으면 그 사건에
    값이 있는데 출력이 null인 필드만 `missed`, 그 사건에 없는 필드는 null이 정답이다.
    """
    matched: dict[str, set[int]] = {}
    for field in HINTS:
        value = normalize(parsed.get(field)) or None
        if value is None or out[field] == "hallucinated":
            continue
        hits = {i for i, ev in enumerate(events) if ev.get(field) and _contains_any(value, ev[field]["any_of"])}
        if hits:
            matched[field] = hits
    if not matched:
        return
    common = set.intersection(*matched.values())
    if not common:
        for field in matched:
            out[field] = "hallucinated"
        return
    for field in HINTS:
        if field in matched:
            out[field] = "correct"
        elif normalize(parsed.get(field)) in (None, ""):
            out[field] = "missed" if all(events[i].get(field) for i in common) else "correct"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _predictions(out: Path):
    for path in sorted(out.glob("*/*.r*.json")):
        if ".judge." not in path.name and ".rule." not in path.name:
            yield path, json.loads(path.read_text(encoding="utf-8"))


def _stratified_sample(cases: dict[str, dict], n: int) -> dict[str, dict]:
    """smoke(#281)용 — `scenario_tag`마다 돌아가며 앞에서부터 하나씩 n개. 매번 같은 케이스가 뽑힌다."""
    by_tag: dict[str, list[str]] = collections.defaultdict(list)
    for case_id, case in cases.items():
        by_tag[case["scenario_tag"]].append(case_id)
    picked: list[str] = []
    queues = [list(ids) for _, ids in sorted(by_tag.items())]
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop(0))
    return {case_id: cases[case_id] for case_id in picked}


def cmd_run(args: argparse.Namespace) -> None:
    from candidates import CandidateAdapter

    cases = load_cases(Path(args.dataset))
    if args.sample:
        cases = _stratified_sample(cases, args.sample)
    out = Path(args.out)

    def run_model(spec: str) -> int:
        # `model@effort`(#281) — effort를 붙이지 않으면 모델 기본값이다. 결과 폴더 · `model_name`은 spec 그대로다.
        model_name, _, effort = spec.partition("@")
        adapter = CandidateAdapter(model_name, system_prompt=CANDIDATE_SYSTEM_PROMPT_V3, reasoning_effort=effort or None)
        written = 0
        for case_id, case in cases.items():
            for k in range(1, args.repeats + 1):
                path = out / spec / f"{case_id}.r{k}.json"
                if path.exists():
                    continue
                r = adapter.extract(case["input_sentence"], case["prior_hints"])
                _write(path, {"case_id": case_id, "scenario_tag": case["scenario_tag"], "prompt": "v3", "repeat": k,
                              "model_name": spec, "reasoning_effort": effort or None, "raw_text": r.raw_text,
                              "parsed": r.parsed, "latency_ms": r.latency_ms, "prompt_tokens": r.prompt_tokens,
                              "completion_tokens": r.completion_tokens, "reasoning_tokens": r.reasoning_tokens,
                              "finish_reason": r.finish_reason, "cost_krw": r.cost_krw, "error": r.error})
                written += 1
                print(f"[{spec}] {case_id} r{k} error={r.error is not None}", flush=True)
        return written

    with ThreadPoolExecutor(max_workers=len(args.models)) as pool:
        print(f"{sum(pool.map(run_model, args.models))}개 기록")


def cmd_rule_score(args: argparse.Namespace) -> None:
    cases = load_cases(Path(args.dataset))
    counts = collections.Counter()
    for path, pred in _predictions(Path(args.out)):
        verdicts = rule_verdicts(cases[pred["case_id"]]["expected"], pred["parsed"])
        _write(path.with_name(path.name.replace(".json", ".rule.json")), {"case_id": pred["case_id"], "verdicts": verdicts})
        counts.update(verdicts.values())
    print(dict(counts))


def _signature(parsed: dict | None) -> str:
    return json.dumps({f: normalize((parsed or {}).get(f)) for f in FIELDS}, sort_keys=True)


def cmd_judge(args: argparse.Namespace) -> None:
    from candidates import JudgeAdapter

    cases = load_cases(Path(args.dataset))
    judge = JudgeAdapter(os.environ["JUDGE_MODEL"])
    done: dict[tuple[str, str], Path] = {}  # (case_id, 출력 서명) → 이미 판정한 파일
    written = reused = 0
    for path, pred in _predictions(Path(args.out)):
        rule = json.loads(path.with_name(path.name.replace(".json", ".rule.json")).read_text(encoding="utf-8"))
        if "unresolved" not in rule["verdicts"].values() or pred["error"]:
            continue
        target = path.with_name(path.name.replace(".json", f".judge.{args.run_id}.json"))
        if target.exists():
            continue
        key = (pred["case_id"], _signature(pred["parsed"]))
        if key in done:  # 같은 케이스에서 출력이 같으면 다시 부르지 않는다
            payload = json.loads(done[key].read_text(encoding="utf-8")) | {"reused_from": done[key].name}
            _write(target, payload)
            reused += 1
            continue
        case = cases[pred["case_id"]]
        for attempt in range(1, 4):  # Elice 경유 구조화 출력이 가끔 스키마를 어긴다
            r = judge.judge(case["input_sentence"], case["prior_hints"], case["expected_notes"], pred["parsed"])
            if not r.error:
                break
        _write(target, {"run_id": args.run_id, "judge_model": judge.model_name, "attempts": attempt,
                        "case_id": pred["case_id"], "parsed": r.parsed, "prompt_tokens": r.prompt_tokens,
                        "completion_tokens": r.completion_tokens, "cost_krw": r.cost_krw, "error": r.error})
        done[key] = target
        written += 1
    print(f"judge 호출 {written}건 · 재사용 {reused}건")


def final_verdicts(path: Path, judge_run_id: str | None) -> dict[str, str]:
    rule = json.loads(path.with_name(path.name.replace(".json", ".rule.json")).read_text(encoding="utf-8"))["verdicts"]
    judged = path.with_name(path.name.replace(".json", f".judge.{judge_run_id}.json")) if judge_run_id else None
    if judged and judged.exists():
        parsed = json.loads(judged.read_text(encoding="utf-8")).get("parsed") or {}
        rule = {f: (parsed[f]["verdict"] if v == "unresolved" and f in parsed else v) for f, v in rule.items()}
    return rule


def cmd_summarize(args: argparse.Namespace) -> None:
    cases = load_cases(Path(args.dataset))
    runs = collections.defaultdict(lambda: collections.defaultdict(list))  # model → case → [(parsed, verdicts, pred)]
    for path, pred in _predictions(Path(args.out)):
        runs[pred["model_name"]][pred["case_id"]].append((pred["parsed"], final_verdicts(path, args.judge_run_id), pred))

    print(f"데이터셋 {args.dataset} · 케이스 {len(cases)} · judge_run_id {args.judge_run_id}\n")
    print("| model | 정확도(평균) | hallucination | missed | 미판정 | 필드 일관성 | 5회 동일 케이스 | 단일 점수 | 통과(hallucination ≤5%) | latency 평균 | 토큰(in/out) | 비용 KRW |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    per_tag = collections.defaultdict(dict)
    for model in sorted(runs):
        verdicts = [v for case_runs in runs[model].values() for _, vs, _ in case_runs for v in vs.values()]
        n = len(verdicts)
        acc = verdicts.count("correct") / n
        hal = verdicts.count("hallucinated") / n
        mis = verdicts.count("missed") / n
        unres = verdicts.count("unresolved") / n
        field_cons, all_same = [], []
        for case_id, case_runs in runs[model].items():
            sigs = [_signature(p) for p, _, _ in case_runs]
            all_same.append(len(set(sigs)) == 1)
            for f in FIELDS:
                values = [normalize((p or {}).get(f)) for p, _, _ in case_runs]
                field_cons.append(collections.Counter(values).most_common(1)[0][1] / len(values))
            tag = cases[case_id]["scenario_tag"]
            per_tag[tag].setdefault(model, []).extend(v for _, vs, _ in case_runs for v in vs.values())
        cons = sum(field_cons) / len(field_cons)
        preds = [p for case_runs in runs[model].values() for _, _, p in case_runs]
        lat = sum(p["latency_ms"] for p in preds) / len(preds)
        tin = sum(p["prompt_tokens"] or 0 for p in preds)
        tout = sum(p["completion_tokens"] or 0 for p in preds)
        # 실행 중에 단가가 등록된 모델도 있어(gemini-3.8-flash, 2026-10-05) 기록된 값 대신 토큰으로 다시 계산한다.
        # `model@effort`(#281)는 단가표에서 모델 이름만 본다.
        costs = [estimate_cost_krw(model.partition("@")[0], p["prompt_tokens"], p["completion_tokens"]) for p in preds]
        cost = f"{sum(costs):.2f}" if all(c is not None for c in costs) else "- (단가 미등록)"
        score = acc * cons
        gate = "통과" if hal <= HALLUCINATION_GATE else "탈락"
        print(f"| {model} | {acc:.1%} | {hal:.1%} | {mis:.1%} | {unres:.1%} | {cons:.1%} | "
              f"{sum(all_same)}/{len(all_same)} | **{score:.3f}** | {gate} | {lat:,.0f}ms | {tin:,}/{tout:,} | {cost} |")

    models = sorted(runs)
    print("\n| 카테고리 | " + " | ".join(models) + " |")
    print("| --- | " + " | ".join("---" for _ in models) + " |")
    for tag in sorted(per_tag):
        cells = []
        for m in models:
            vs = per_tag[tag].get(m, [])
            cells.append(f"{vs.count('correct') / len(vs):.0%}" if vs else "-")
        print(f"| {tag} | " + " | ".join(cells) + " |")

    if args.judge_run_id:
        jfiles = [p for p in Path(args.out).glob(f"*/*.judge.{args.judge_run_id}.json")]
        called = [json.loads(p.read_text(encoding="utf-8")) for p in jfiles]
        called = [j for j in called if "reused_from" not in j]
        jcost = sum(j.get("cost_krw") or 0 for j in called)
        print(f"\njudge 호출 {len(called)}건 · 비용 {jcost:.2f} KRW")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, func in (("run", cmd_run), ("rule-score", cmd_rule_score), ("judge", cmd_judge), ("summarize", cmd_summarize)):
        s = sub.add_parser(name)
        s.set_defaults(func=func)
        s.add_argument("--dataset", default=DEFAULT_DATASET)
        s.add_argument("--out", default=DEFAULT_OUT)
        if name == "run":
            s.add_argument("--models", nargs="+", required=True)
            s.add_argument("--repeats", type=int, default=5)
            s.add_argument("--sample", type=int, help="smoke — scenario_tag별로 고르게 n케이스만(#281)")
        if name == "judge":
            s.add_argument("--run-id", required=True)
        if name == "summarize":
            s.add_argument("--judge-run-id")
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
