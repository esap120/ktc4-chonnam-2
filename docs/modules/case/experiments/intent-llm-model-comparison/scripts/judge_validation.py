"""judge 신뢰도 검증 — 표본 추출 · 판정 일치도 계산(멘토 피드백 2026-10-04 Q1).

지금까지의 「스팟체크」는 judge가 `correct`가 아니라고 한 판정만 읽었고, 사람과 judge의 일치도를
잰 적이 없다(`decisions/intent-llm-model-selection.md` §9, `research/intent-llm-robustness-test-design.md`
§14). 이 스크립트는 그 일치도를 잰다.

사용:
    # 1) 표본 추출 — judge 판정을 뺀 항목 파일(items.jsonl)과 판정 key(key.jsonl)를 따로 쓴다
    python scripts/judge_validation.py sample \\
        --dataset datasets/intent-hint-robustness-v2.jsonl \\
        --predictions predictions-robustness-v2 --judge-run-id 20260922T124511Z \\
        --out-dir judge-validation-v2

    # 2) 판정자 라벨(labels/<rater>.jsonl, 줄마다 {"item_id", "verdict", "reason"})과 key의 일치도
    python scripts/judge_validation.py agree --out-dir judge-validation-v2 --a labels/ai-opus-5-5.jsonl --b key.jsonl

표본은 판정 종류별로 나눠 뽑는다 — judge 판정의 88%가 `correct`라 무작위로 뽑으면 judge가
틀리기 쉬운 비-`correct` 판정을 거의 보지 못한다. 카테고리 · 모델도 고르게 섞고, 항목 순서는
섞어서 판정 종류가 몰려 있지 않게 한다.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

from dataset import load_dataset
from schema import FIELDS, VERDICTS

# 비-correct 40개의 판정 종류별 몫 — 실제 분포(hallucinated 84 · partial 42 · missed 9)를 따르되
# missed가 너무 적게 뽑히지 않게 최소 몫을 둔다.
_OTHER_QUOTA = {"hallucinated": 22, "partial": 12, "missed": 6}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _load_verdicts(dataset_path: Path, predictions_dir: Path, run_id: str) -> list[dict]:
    cases = {c.id: c for c in load_dataset(dataset_path)}
    rows = []
    for judge_file in sorted(predictions_dir.glob(f"*/*.judge.{run_id}.json")):
        model_name = judge_file.parent.name
        case_id = judge_file.name.split(".judge.")[0]
        judged = json.loads(judge_file.read_text(encoding="utf-8"))
        verdicts = judged.get("parsed") or json.loads(judged["raw_text"])
        prediction = json.loads((judge_file.parent / f"{case_id}.json").read_text(encoding="utf-8"))
        case = cases[case_id]
        for field in FIELDS:
            rows.append(
                {
                    "case_id": case_id,
                    "scenario_tag": case.scenario_tag,
                    "model_name": model_name,
                    "field": field,
                    "input_sentence": case.input_sentence,
                    "prior_hints": case.prior_hints,
                    "expected_notes": case.expected_notes,
                    "candidate_output": prediction.get("parsed"),
                    "judge_verdict": verdicts[field]["verdict"],
                    "judge_reason": verdicts[field]["reason"],
                }
            )
    return rows


def _spread(rows: list[dict], n: int, rng: random.Random) -> list[dict]:
    """카테고리 → 모델 순으로 돌아가며 뽑아 한쪽에 몰리지 않게 한다."""
    by_tag: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        by_tag[row["scenario_tag"]].append(row)
    for bucket in by_tag.values():
        # 카테고리 안에서는 모델마다 몇 번째로 나왔는지를 기준으로 정렬해 모델이 번갈아 나오게 한다.
        rng.shuffle(bucket)
        seen: collections.Counter[str] = collections.Counter()
        ranked = []
        for r in bucket:
            ranked.append((seen[r["model_name"]], r))
            seen[r["model_name"]] += 1
        bucket[:] = [r for _, r in sorted(ranked, key=lambda x: x[0])]
    picked: list[dict] = []
    tags = sorted(by_tag)
    rng.shuffle(tags)
    while len(picked) < n and any(by_tag.values()):
        for tag in tags:
            if by_tag[tag] and len(picked) < n:
                picked.append(by_tag[tag].pop(0))
    return picked


def cmd_sample(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    rows = _load_verdicts(Path(args.dataset), Path(args.predictions), args.judge_run_id)
    sample = _spread([r for r in rows if r["judge_verdict"] == "correct"], args.n_correct, rng)
    for verdict, quota in _OTHER_QUOTA.items():
        sample += _spread([r for r in rows if r["judge_verdict"] == verdict], quota, rng)
    rng.shuffle(sample)

    out = Path(args.out_dir)
    items, key = [], []
    for i, row in enumerate(sample, start=1):
        item_id = f"jv-{i:03d}"
        items.append({"item_id": item_id, **{k: v for k, v in row.items() if not k.startswith("judge_")}})
        key.append({"item_id": item_id, "verdict": row["judge_verdict"], "reason": row["judge_reason"]})
    _write_jsonl(out / "items.jsonl", items)
    _write_jsonl(out / "key.jsonl", key)
    meta = {
        "judge_run_id": args.judge_run_id,
        "seed": args.seed,
        "n_correct": args.n_correct,
        "other_quota": _OTHER_QUOTA,
        "population": dict(collections.Counter(r["judge_verdict"] for r in rows)),
    }
    (out / "sample-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"items {len(items)} → {out / 'items.jsonl'} (judge 판정은 {out / 'key.jsonl'})")


def cohen_kappa(a: list[str], b: list[str], labels: tuple[str, ...]) -> float:
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    expected = sum(ca[label] * cb[label] for label in labels) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(a: dict[str, str], b: dict[str, str]) -> dict:
    ids = sorted(set(a) & set(b))
    va, vb = [a[i] for i in ids], [b[i] for i in ids]
    ba = ["correct" if v == "correct" else "not_correct" for v in va]
    bb = ["correct" if v == "correct" else "not_correct" for v in vb]
    confusion = collections.Counter(zip(va, vb, strict=True))
    return {
        "n": len(ids),
        "agreement_4class": sum(x == y for x, y in zip(va, vb, strict=True)) / len(ids),
        "kappa_4class": cohen_kappa(va, vb, VERDICTS),
        "agreement_binary": sum(x == y for x, y in zip(ba, bb, strict=True)) / len(ids),
        "kappa_binary": cohen_kappa(ba, bb, ("correct", "not_correct")),
        "confusion": {f"{x}|{y}": c for (x, y), c in sorted(confusion.items())},
        "disagreements": [i for i in ids if a[i] != b[i]],
    }


def cmd_agree(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    a = {r["item_id"]: r["verdict"] for r in _read_jsonl(out / args.a)}
    b = {r["item_id"]: r["verdict"] for r in _read_jsonl(out / args.b)}
    print(json.dumps(agreement(a, b), ensure_ascii=False, indent=2))


def cmd_export(args: argparse.Namespace) -> None:
    """표본 항목(items.jsonl)에 대해 다른 judge run의 판정을 key와 같은 모양으로 꺼낸다 — `agree`로 비교한다."""
    out = Path(args.out_dir)
    rows = _load_verdicts(Path(args.dataset), Path(args.predictions), args.judge_run_id)
    by_key = {(r["model_name"], r["case_id"], r["field"]): r for r in rows}
    exported, missing = [], []
    for item in _read_jsonl(out / "items.jsonl"):
        row = by_key.get((item["model_name"], item["case_id"], item["field"]))
        if row is None:
            missing.append(item["item_id"])
            continue
        exported.append({"item_id": item["item_id"], "verdict": row["judge_verdict"], "reason": row["judge_reason"]})
    _write_jsonl(out / args.name, exported)
    print(f"{len(exported)}개 → {out / args.name}" + (f" (판정 없음 {missing})" if missing else ""))


_HINT_FIELDS = ("time_hint", "vehicle_hint", "situation_hint", "location_hint")


def prior_null_penalties(rows: list[dict]) -> list[dict]:
    """정정 케이스에서 judge가 올바른 null을 틀렸다고 한 판정 후보.

    판정 기준은 「이번 발화에서 언급하지 않은 필드는 prior_hints에 값이 있어도 null(복사하면 hallucinated)」인데,
    judge가 「이전 값을 유지했어야 한다」며 missed · hallucinated를 준 사례가 사람 판정으로 확인됐다(jv-036 ·
    jv-070). 조건: prior_hints에 그 필드 값이 있고, 모델이 null로 뒀고, judge가 correct가 아니라고 했다.
    모델이 원문에 있는 값을 실제로 놓친 경우도 같은 조건에 걸리므로 `--exclude`로 사람이 확인해 뺀다.
    """
    return [
        r
        for r in rows
        if r["field"] in _HINT_FIELDS
        and (r["prior_hints"] or {}).get(r["field"])
        and (r["candidate_output"] or {}).get(r["field"]) is None
        and r["judge_verdict"] != "correct"
    ]


def cmd_scan(args: argparse.Namespace) -> None:
    rows = _load_verdicts(Path(args.dataset), Path(args.predictions), args.judge_run_id)
    excluded = set(args.exclude or [])
    flagged = [r for r in prior_null_penalties(rows) if f'{r["model_name"]}/{r["case_id"]}/{r["field"]}' not in excluded]
    flagged_keys = {(r["model_name"], r["case_id"], r["field"]) for r in flagged}
    for r in flagged:
        print(f'{r["model_name"]}/{r["case_id"]}/{r["field"]}  judge={r["judge_verdict"]}  {r["judge_reason"][:90]}')

    def acc(subset: list[dict], fixed: bool) -> float:
        good = sum(
            r["judge_verdict"] == "correct" or (fixed and (r["model_name"], r["case_id"], r["field"]) in flagged_keys)
            for r in subset
        )
        return good / len(subset)

    print(f"\n대상 {len(flagged)}건 · 모델별 field 정확도 (judge 원래 → 대상만 correct로 바로잡음)")
    for model in sorted({r["model_name"] for r in rows}):
        mine = [r for r in rows if r["model_name"] == model]
        by_tag = collections.defaultdict(list)
        for r in mine:
            by_tag[r["scenario_tag"]].append(r)
        tags = sorted({r["scenario_tag"] for r in mine if (r["model_name"], r["case_id"], r["field"]) in flagged_keys})
        detail = " · ".join(f"{t} {acc(by_tag[t], False):.0%}→{acc(by_tag[t], True):.0%}" for t in tags)
        print(f"{model:24s} 전체 {acc(mine, False):.1%}→{acc(mine, True):.1%}  {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--dataset", required=True)
    s.add_argument("--predictions", required=True)
    s.add_argument("--judge-run-id", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--n-correct", type=int, default=40)
    s.add_argument("--seed", type=int, default=20261004)
    s.set_defaults(func=cmd_sample)
    g = sub.add_parser("agree")
    g.add_argument("--out-dir", required=True)
    g.add_argument("--a", required=True)
    g.add_argument("--b", required=True)
    g.set_defaults(func=cmd_agree)
    c = sub.add_parser("scan", help="정정 케이스에서 올바른 null을 틀렸다고 한 judge 판정을 찾고 정확도를 다시 계산")
    c.add_argument("--dataset", required=True)
    c.add_argument("--predictions", required=True)
    c.add_argument("--judge-run-id", required=True)
    c.add_argument("--exclude", nargs="*", help="model/case_id/field — 모델이 실제로 놓친 것으로 사람이 확인한 항목")
    c.set_defaults(func=cmd_scan)
    e = sub.add_parser("export", help="표본 항목에 대한 다른 judge run의 판정을 key 모양으로 꺼낸다")
    e.add_argument("--dataset", required=True)
    e.add_argument("--predictions", required=True)
    e.add_argument("--judge-run-id", required=True)
    e.add_argument("--out-dir", required=True)
    e.add_argument("--name", required=True, help="예: key-opus5.jsonl")
    e.set_defaults(func=cmd_export)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
