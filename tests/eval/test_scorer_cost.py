"""비용 집계.

정본 집계 키는 case_id 다 (usage-record/v1.2 §9-2). run_ref 로 묶으면
run 이 산출되지 않은 attempt(run_ref=null, RUN_NOT_PRODUCED)가 통째로
빠져 비용이 과소 보고된다.
"""
import pytest

from eval.scorers import cost


def _row(case_id, amount, currency="KRW", run_ref=None, reason=None):
    return {"case_id": case_id, "cost": {"amount": amount, "currency": currency},
            "run_ref": run_ref, "run_ref_reason": reason}


def test_aggregates_by_case_id_not_by_run_ref():
    rows = [
        _row("case_a", "100", run_ref={"kind": "analysis_run", "ref": "run_a"}),
        _row("case_a", "50", run_ref=None, reason="RUN_NOT_PRODUCED"),
        _row("case_b", "30", run_ref=None, reason="DIRECT_NO_RUN"),
    ]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["cost_per_case"] == {"case_a": 150.0, "case_b": 30.0}
    assert out["total"] == 180.0
    assert out["currency"] == "KRW"


def test_cost_per_source_video_hour_uses_the_given_denominator():
    rows = [_row("case_a", "1200")]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])
    assert out["cost_per_source_video_hour"] == pytest.approx(1200.0)


def test_zero_cost_case_is_kept_not_dropped():
    """0원 case 를 빼면 분포가 왜곡된다 — 평균만 보면 안 보인다."""
    rows = [_row("case_a", "100"), _row("case_x", "0")]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])
    assert out["cost_per_case"]["case_x"] == 0.0


def test_mixed_currency_is_refused_not_converted():
    """환율은 pricing_context 에 귀속되지 eval 이 정할 값이 아니다."""
    rows = [_row("case_a", "100", "KRW"), _row("case_b", "1", "USD")]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] is None
    assert "MIXED_CURRENCY" in out["coverage"]


def test_no_usage_rows_returns_null_not_zero():
    out = cost.score([], processed_duration_sec=3600.0, scenarios=[])
    assert out["total"] is None
    assert "NO_USAGE_RECORDS" in out["coverage"]


def test_no_duration_leaves_the_hourly_rate_null():
    rows = [_row("case_a", "100")]
    out = cost.score(rows, processed_duration_sec=None, scenarios=["s1"])
    assert out["total"] == 100.0
    assert out["cost_per_source_video_hour"] is None


def test_missing_duration_reason_differs_from_zero_duration_reason():
    """None(기록 없음)과 0(실측된 무값)은 다른 사실이다 — 사유 문구도 달라야 한다."""
    rows = [_row("case_a", "100")]

    missing = cost.score(rows, processed_duration_sec=None, scenarios=["s1"])
    zero = cost.score(rows, processed_duration_sec=0.0, scenarios=["s1"])

    assert missing["cost_per_source_video_hour"] is None
    assert zero["cost_per_source_video_hour"] is None
    assert missing["coverage"] != zero["coverage"]
    assert "NO_PROCESSED_DURATION" in missing["coverage"]
    assert "ZERO_PROCESSED_DURATION" in zero["coverage"]


# --- 속도 (멘토 피드백 2026-09-20 「비용에 더해 속도도 함께 보시길」) ---
#
# latency_ms 는 usage-record/v1.2 §9-4 가 이미 필수 키로 두고 있고
# mock pack 에도 값이 들어 있다. 여기서 새로 만드는 값이 아니라
# 버리고 있던 값을 읽는 것이다.


def _lrow(case_id, amount, latency_ms, currency="KRW"):
    r = _row(case_id, amount, currency)
    r["latency_ms"] = latency_ms
    return r


def test_latency_reports_the_distribution_not_only_the_mean():
    """평균 하나로는 「대부분 빠른데 가끔 30초」가 안 보인다."""
    rows = [_lrow("c%d" % i, "10", ms) for i, ms in
            enumerate([100, 200, 300, 400, 500, 600, 700, 800, 900, 30000])]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    lat = out["latency_ms"]
    assert lat["p50"] == 500
    assert lat["p90"] == 900          # nearest-rank: 10건의 90% 지점은 9번째
    assert lat["max"] == 30000
    assert lat["n"] == 10


def test_no_latency_anywhere_is_null_not_zero():
    """기록이 없는 것과 0ms 로 빨랐던 것은 다른 사실이다."""
    rows = [_row("case_a", "100")]          # latency_ms 키 자체가 없다
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["latency_ms"]["p50"] is None
    assert out["latency_ms"]["n"] == 0
    assert "NO_LATENCY" in out["coverage"]


def test_rows_without_latency_are_counted_not_silently_dropped():
    """분모가 조용히 줄면 「전부 빨랐다」로 읽힌다."""
    rows = [_lrow("case_a", "10", 100), _lrow("case_b", "10", None),
            _row("case_c", "10")]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["latency_ms"]["n"] == 1
    assert out["latency_ms"]["n_missing"] == 2
    assert "PARTIAL_LATENCY" in out["coverage"]


def test_latency_per_source_video_hour_is_call_time_not_wall_clock():
    """호출이 병렬이면 합은 경과시간이 아니다. 합으로 정의하고 그렇게 부른다."""
    rows = [_lrow("case_a", "10", 60000), _lrow("case_b", "10", 60000)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    # 영상 1시간을 처리하는 데 든 총 호출 대기 시간 = 120초
    assert out["latency_per_source_video_hour"] == pytest.approx(120.0)


def test_latency_hourly_rate_is_null_without_a_denominator():
    rows = [_lrow("case_a", "10", 100)]
    out = cost.score(rows, processed_duration_sec=None, scenarios=["s1"])
    assert out["latency_per_source_video_hour"] is None


def test_no_usage_rows_keeps_every_latency_key():
    """키가 사라지면 결과 파일을 기계로 비교할 수 없다."""
    out = cost.score([], processed_duration_sec=3600.0, scenarios=[])
    assert out["latency_ms"] == {"p50": None, "p90": None, "max": None,
                                 "n": 0, "n_missing": 0}
    assert out["latency_per_source_video_hour"] is None


def test_mixed_currency_still_reports_latency():
    """통화가 섞인 것은 비용의 문제지 속도의 문제가 아니다."""
    rows = [_lrow("case_a", "100", 500, "KRW"), _lrow("case_b", "1", 700, "USD")]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] is None
    assert out["latency_ms"]["p50"] == 500


# --- 비용을 알 수 없는 호출 (이슈 #107) ---
#
# 호출은 실제로 일어났고 시간도 걸렸는데 provider 응답의 토큰 usage 만
# 파싱 실패하는 경우가 있다. 그 row 를 통째로 버리면 분자만 줄고 분모
# (processed_duration_sec)는 그대로라 시간당 비용이 실제보다 낮게 나온다.
# 계약도 「invocation 이 시작됐을 때 row 를 만든다」로 정해 두었다
# (contract-usage-record.md §9-6).


def _norow(case_id, latency_ms=None):
    r = {"case_id": case_id, "cost": None}
    if latency_ms is not None:
        r["latency_ms"] = latency_ms
    return r


def test_a_call_with_unknown_cost_does_not_vanish_from_the_report():
    rows = [_lrow("case_a", "100", 500), _norow("case_b", 700)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["n_rows"] == 2
    assert out["n_unknown_cost"] == 1
    assert "UNKNOWN_COST" in out["coverage"]


def test_unknown_cost_rows_are_excluded_from_the_cost_total():
    """비용을 모르는 것을 0원으로 세면 「쌌다」로 읽힌다."""
    rows = [_lrow("case_a", "100", 500), _norow("case_b", 700)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] == 100.0
    assert "case_b" not in out["cost_per_case"]


def test_unknown_cost_rows_still_count_toward_speed():
    """비용을 못 쟀다고 그 호출이 안 걸린 것은 아니다."""
    rows = [_lrow("case_a", "100", 500), _norow("case_b", 700)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["latency_ms"]["n"] == 2
    assert out["latency_ms"]["max"] == 700


def test_every_row_unknown_leaves_cost_null_not_zero():
    rows = [_norow("case_a", 500), _norow("case_b", 700)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] is None
    assert out["cost_per_source_video_hour"] is None
    assert out["n_unknown_cost"] == 2
    assert out["latency_ms"]["p50"] == 500        # 속도는 여전히 나온다


def test_no_unknown_cost_rows_means_no_reason_and_a_zero_counter():
    rows = [_lrow("case_a", "100", 500)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["n_unknown_cost"] == 0
    assert "UNKNOWN_COST" not in (out["coverage"] or "")


def test_no_usage_rows_keeps_the_unknown_cost_counter():
    out = cost.score([], processed_duration_sec=3600.0, scenarios=[])
    assert out["n_unknown_cost"] == 0


# #244 (RD-18 U-2·U-4): KRW 요율이 없거나 실패 호출 과금을 모르면 cost 객체는
# 있지만 amount 가 null 이다. cost=None 과 같은 「모른다」로 세야 한다.
def test_null_amount_is_unknown_cost_not_a_crash():
    rows = [_lrow("case_a", "100", 500), _row("case_b", None)]
    out = cost.score(rows, processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] == 100.0
    assert out["n_unknown_cost"] == 1
    assert "case_b" not in out["cost_per_case"]
    assert "UNKNOWN_COST" in out["coverage"]


def test_every_amount_null_leaves_cost_null_not_zero():
    out = cost.score([_row("case_a", None), _row("case_b", None)],
                     processed_duration_sec=3600.0, scenarios=["s1"])

    assert out["total"] is None
    assert out["cost_per_source_video_hour"] is None
    assert out["n_unknown_cost"] == 2
