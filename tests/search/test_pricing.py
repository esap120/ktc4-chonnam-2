"""Tests for injected pricing (Task 4)."""

from decimal import Decimal

import pytest

from daesingo.search.config import GeminiSearchConfig
from daesingo.search.usage import ProviderUsage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INPUT_RATE = 0.75
_OUTPUT_RATE = 3.75
_MAX_COST = 1.0


def _cfg(
    input_usd_per_million: float = _INPUT_RATE,
    output_usd_per_million: float = _OUTPUT_RATE,
    max_cost_usd: float = _MAX_COST,
) -> GeminiSearchConfig:
    return GeminiSearchConfig(
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
        max_cost_usd=max_cost_usd,
    )


def _usage(inp: int | None, out: int | None, thought: int | None) -> ProviderUsage:
    if inp is not None and out is not None and thought is not None:
        total: int | None = inp + out + thought
    else:
        total = None
    return ProviderUsage(
        input_tokens=inp,
        output_tokens=out,
        thought_tokens=thought,
        total_tokens=total,
    )


# ---------------------------------------------------------------------------
# Config: fingerprint changes when each pricing field changes
# ---------------------------------------------------------------------------


class TestConfigFingerprint:
    def test_baseline_is_stable(self) -> None:
        cfg = _cfg()
        assert cfg.fingerprint == cfg.fingerprint
        assert cfg.fingerprint != _cfg(input_usd_per_million=99.0).fingerprint

    def test_changes_on_input_rate(self) -> None:
        assert _cfg().fingerprint != _cfg(input_usd_per_million=1.0).fingerprint

    def test_changes_on_output_rate(self) -> None:
        assert _cfg().fingerprint != _cfg(output_usd_per_million=5.0).fingerprint

    def test_changes_on_max_cost_usd(self) -> None:
        assert _cfg().fingerprint != _cfg(max_cost_usd=2.0).fingerprint


# ---------------------------------------------------------------------------
# Config: validation of pricing fields
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_negative_input_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="input_usd_per_million"):
            _ = _cfg(input_usd_per_million=-0.01)

    def test_negative_output_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="output_usd_per_million"):
            _ = _cfg(output_usd_per_million=-1.0)

    def test_negative_max_cost_raises(self) -> None:
        with pytest.raises(ValueError, match="max_cost_usd"):
            _ = _cfg(max_cost_usd=-0.01)

    def test_inf_input_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="input_usd_per_million"):
            _ = _cfg(input_usd_per_million=float("inf"))

    def test_nan_output_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="output_usd_per_million"):
            _ = _cfg(output_usd_per_million=float("nan"))

    def test_zero_rates_are_valid(self) -> None:
        cfg = GeminiSearchConfig()  # all pricing defaults are 0.0
        assert cfg.input_usd_per_million == 0.0
        assert cfg.output_usd_per_million == 0.0


# ---------------------------------------------------------------------------
# ProviderUsage.cost_with_rates: exact Decimal math
# ---------------------------------------------------------------------------


class TestCostWithRates:
    def test_exact_decimal_for_known_tokens(self) -> None:
        usage = _usage(1_000_000, 100_000, 50_000)
        cost = usage.cost_with_rates(0.75, 3.75)
        assert cost is not None
        # input: 1_000_000 * 0.75 / 1_000_000 = 0.75
        # output+thought: 150_000 * 3.75 / 1_000_000 = 0.5625
        assert cost == Decimal("0.75") + Decimal("0.5625")

    def test_zero_tokens_gives_zero_cost(self) -> None:
        usage = _usage(0, 0, 0)
        assert usage.cost_with_rates(0.75, 3.75) == Decimal(0)

    def test_missing_input_tokens_returns_none(self) -> None:
        assert _usage(None, 100, 50).cost_with_rates(0.75, 3.75) is None

    def test_missing_output_tokens_returns_none(self) -> None:
        assert _usage(100, None, 50).cost_with_rates(0.75, 3.75) is None

    def test_missing_thought_tokens_returns_none(self) -> None:
        assert _usage(100, 100, None).cost_with_rates(0.75, 3.75) is None

    def test_result_is_decimal_not_float(self) -> None:
        cost = _usage(500_000, 200_000, 10_000).cost_with_rates(0.75, 3.75)
        assert isinstance(cost, Decimal)


def test_unset_rates_are_unknown_cost_not_zero() -> None:
    """기본 단가 0.0은 미설정이다 — 0원으로 쓰지 않는다(#153)."""
    assert _usage(100, 50, 0).cost_with_rates(0.0, 0.0) is None
