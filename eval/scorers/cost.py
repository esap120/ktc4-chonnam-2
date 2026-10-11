"""비용 지표.

정본 집계 키는 case_id 다 (contract-usage-record.md §9-2). run_ref 는
per-run 감사용이며, run 이 산출되지 않은 attempt(run_ref=null,
RUN_NOT_PRODUCED)는 run_ref 로 묶으면 통째로 빠져 비용이 과소 보고된다.

분모(processed_duration_sec)는 호출부가 넘긴다. 이 모듈은 파일을 읽지
않는다 — 분자와 분모가 같은 시나리오 집합에서 나왔는지는 넘기는 쪽이
보장한다.

**속도도 여기서 낸다** (2026-09-20 멘토 피드백 「비용에 더해 속도도 함께」).
`latency_ms` 는 usage-record/v1.2 §9-4 가 이미 필수 키로 둔 값이고 mock
pack 에도 들어 있다 — 새로 만드는 값이 아니라 버리고 있던 값을 읽는다.
비용과 같은 row 에서 나오므로 같은 집계에 둔다.
"""
import math

SCORER_VERSION = "c3"   # 2026-09-20 비용 미상 row 를 버리지 않는다 (이슈 #107)

NO_ROWS = "NO_USAGE_RECORDS — 이 실행에 비용 기록이 없다"
MIXED = ("MIXED_CURRENCY — 통화가 섞여 합산하지 않는다. 환율은 "
         "pricing_context 에 귀속되며 eval 이 정할 값이 아니다")
ZERO_DURATION = ("ZERO_PROCESSED_DURATION — 분모가 0이라 시간당 환산치를 "
                  "낼 수 없다 (기록이 없다는 뜻이 아니다)")
NO_LATENCY = ("NO_LATENCY — 어느 row 에도 latency_ms 가 없다. 빨랐다는 뜻이 "
              "아니라 재지 않았다는 뜻이다")


def _priced(usage_records):
    """비용을 아는 row 만. 나머지는 「0원」이 아니라 「모른다」다.

    호출은 실제로 일어났는데 provider 응답의 토큰 usage 만 파싱 실패하는
    경우가 있다. 그 row 를 아예 안 넘겨 버리면 분자만 줄고 분모
    (processed_duration_sec)는 그대로라 시간당 비용이 조용히 낮아진다.
    그렇다고 0원으로 세면 「쌌다」가 된다 — 세지 않되 몇 건인지는 남긴다.

    cost 객체는 있는데 amount 가 null 인 row 도 같은 「모른다」다. KRW 요율이
    없거나 실패 호출의 과금을 확인하기 전에는 그렇게 기록된다 (#244 RD-18).
    """
    return [r for r in usage_records
            if r.get("cost") is not None and r["cost"].get("amount") is not None]


def _nearest_rank(values, q):
    """정렬된 값에서 q 분위. 보간하지 않는다.

    보간하면 「실제로 일어나지 않은 지연 시간」이 결과 파일에 적힌다.
    호출 건수가 적을 때 특히 그렇다. 실측값 중 하나를 고른다.
    """
    return values[max(0, math.ceil(q * len(values)) - 1)]


def _latency(usage_records, processed_duration_sec):
    """호출 지연 분포와 영상 시간당 총 호출 대기 시간.

    **latency_per_source_video_hour 는 경과시간이 아니다.** 호출이 병렬로
    돌면 합은 벽시계를 넘는다. 「영상 1시간을 처리하는 데 든 총 호출 대기
    시간(초)」이며, 그 이상을 주장하지 않는다.
    """
    got = sorted(int(r["latency_ms"]) for r in usage_records
                 if r.get("latency_ms") is not None)
    missing = len(usage_records) - len(got)
    dist = {
        "p50": _nearest_rank(got, 0.5) if got else None,
        "p90": _nearest_rank(got, 0.9) if got else None,
        "max": got[-1] if got else None,
        "n": len(got),
        "n_missing": missing,
    }
    hourly = None
    if got and processed_duration_sec:
        hourly = (sum(got) / 1000.0) / (processed_duration_sec / 3600.0)

    reasons = []
    if usage_records and not got:
        reasons.append(NO_LATENCY)
    elif missing:
        reasons.append(
            "PARTIAL_LATENCY — %d/%d row 에 latency_ms 가 없어 분포에서 뺐다"
            % (missing, len(usage_records)))
    return dist, hourly, reasons


def score(usage_records, processed_duration_sec, scenarios):
    # 속도는 비용이 멈추는 자리에서도 낸다 — 통화가 섞인 것은 비용의
    # 문제지 속도의 문제가 아니다.
    lat, lat_hourly, lat_reasons = _latency(usage_records, processed_duration_sec)
    # 속도는 모든 row 에서 낸다 — 비용을 못 쟀다고 그 호출이 안 걸린 것은 아니다.
    priced = _priced(usage_records)
    n_unknown = len(usage_records) - len(priced)
    unknown_reason = (
        ["UNKNOWN_COST — 비용을 알 수 없는 호출 %d건을 비용 집계에서 뺐다 "
         "(0원이 아니라 모른다). 이 호출들도 실제로 일어났고 속도 집계에는 들어간다"
         % n_unknown] if n_unknown else [])

    if not usage_records:
        return {"cost_per_case": None, "cost_per_source_video_hour": None,
                "total": None, "currency": None, "n_rows": 0,
                "n_unknown_cost": 0,
                "latency_ms": lat, "latency_per_source_video_hour": lat_hourly,
                "scenarios": list(scenarios), "coverage": NO_ROWS,
                "scorer_version": SCORER_VERSION}

    if not priced:
        # 호출은 있었는데 비용을 하나도 모른다. 0 이 아니라 null 이다.
        return {"cost_per_case": None, "cost_per_source_video_hour": None,
                "total": None, "currency": None, "n_rows": len(usage_records),
                "n_unknown_cost": n_unknown,
                "latency_ms": lat, "latency_per_source_video_hour": lat_hourly,
                "scenarios": list(scenarios),
                "coverage": "; ".join(unknown_reason + lat_reasons),
                "scorer_version": SCORER_VERSION}

    currencies = {r["cost"]["currency"] for r in priced}
    if len(currencies) > 1:
        return {"cost_per_case": None, "cost_per_source_video_hour": None,
                "total": None, "currency": sorted(currencies),
                "n_rows": len(usage_records), "n_unknown_cost": n_unknown,
                "latency_ms": lat, "latency_per_source_video_hour": lat_hourly,
                "scenarios": list(scenarios),
                "coverage": "; ".join([MIXED] + unknown_reason + lat_reasons),
                "scorer_version": SCORER_VERSION}

    per_case = {}
    for r in priced:
        case_id = r["case_id"]
        per_case[case_id] = per_case.get(case_id, 0.0) + float(r["cost"]["amount"])

    total = sum(per_case.values())
    hourly = None
    if processed_duration_sec is not None and processed_duration_sec != 0:
        hourly = total / (processed_duration_sec / 3600.0)

    reasons = []
    zero_cases = sorted(c for c, v in per_case.items() if v == 0.0)
    if zero_cases:
        # 평균만 보면 안 보인다. 0원 case 가 있다는 사실을 파일에 남긴다.
        reasons.append("ZERO_COST_CASES — %s" % ", ".join(zero_cases))
    reasons.extend(unknown_reason)
    if processed_duration_sec is None:
        reasons.append("NO_PROCESSED_DURATION — 시간당 환산치를 낼 수 없다")
    elif processed_duration_sec == 0:
        reasons.append(ZERO_DURATION)
    reasons.extend(lat_reasons)

    return {
        "cost_per_case": per_case,
        "cost_per_source_video_hour": hourly,
        "total": total,
        "currency": currencies.pop(),
        "n_rows": len(usage_records),
        "n_unknown_cost": n_unknown,
        "latency_ms": lat,
        "latency_per_source_video_hour": lat_hourly,
        "scenarios": list(scenarios),
        "coverage": "; ".join(reasons) if reasons else None,
        "scorer_version": SCORER_VERSION,
    }
