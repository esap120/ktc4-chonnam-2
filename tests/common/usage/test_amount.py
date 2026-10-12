"""Exact amount boundaries must reject rather than let MySQL round."""

from decimal import Decimal, localcontext
from importlib import import_module

import pytest


def amounts():
    return import_module("daesingo.common.usage.amount")


@pytest.mark.parametrize("value,want", [
    (None, None), ("0", Decimal("0")), (Decimal("0"), Decimal("0")),
    ("184.20", Decimal("184.20")), ("0.000000000000000000000000000001", Decimal("1E-30")),
    ("9" * 35 + "." + "9" * 30, Decimal("9" * 35 + "." + "9" * 30)),
    ("-184.20", Decimal("-184.20")), ("1e34", Decimal("1e34")),
])
def test_exact_range_and_unknown_are_preserved(value, want):
    with localcontext() as context:
        context.prec = 3
        assert amounts().parse_amount(value) == want
        text = amounts().amount_string(value)
        assert text is None if want is None else Decimal(text) == want


@pytest.mark.parametrize("value", [
    0.0, 184.2, 0, 1, True, False, [], {},
])
def test_only_decimal_and_string_are_accepted(value):
    with pytest.raises(TypeError, match="amount"):
        amounts().parse_amount(value)


@pytest.mark.parametrize("value", [
    "1e35", "-1e35", "0." + "0" * 30 + "1", Decimal("1e-31"),
    "1." + "0" * 31, "0." + "0" * 31, "NaN", "sNaN", "Infinity", "-Infinity",
    "", "not_decimal", " 1.2", "1_000", "１２.３", "1\n", "1e" + "9" * 30,
])
def test_excess_digits_and_nonfinite_or_malformed_values_are_rejected(value):
    with pytest.raises(ValueError, match="amount"):
        amounts().parse_amount(value)


def test_serialization_never_uses_context_rounding_or_float_and_distinguishes_zero():
    value = Decimal("12345678901234567890123456789012345.123456789012345678901234567891")
    with localcontext() as context:
        context.prec = 2
        assert amounts().amount_string(value) == str(value)
        assert amounts().amount_string(None) is None
        assert amounts().amount_string("0.00000") == "0"
        assert amounts().amount_string("184.20") == "184.2"
