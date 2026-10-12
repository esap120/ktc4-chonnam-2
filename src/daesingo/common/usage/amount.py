"""Exact KRW snapshot representation; never quantize or convert through float."""

from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import DECIMAL
from sqlalchemy.types import TypeDecorator

AMOUNT_PRECISION = 65
AMOUNT_SCALE = 30
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def parse_amount(value: Decimal | str | None) -> Decimal | None:
    """Reject excess declared scale, even zero suffixes, before DB coercion.

    Tuple/exponent inspection does not depend on the current Decimal context.
    Bounds are the physical DECIMAL(65,30) range, not a pricing policy.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if _DECIMAL.fullmatch(value) is None:
            raise ValueError("invalid amount")
        try:
            value = Decimal(value)
        except InvalidOperation:
            raise ValueError("invalid amount") from None
    elif not isinstance(value, Decimal):
        raise TypeError("amount requires Decimal or decimal string")
    if not value.is_finite():
        raise ValueError("invalid amount")
    digits = value.as_tuple()
    if digits.exponent < -AMOUNT_SCALE:
        raise ValueError("amount exceeds scale")
    if not value.is_zero() and len(digits.digits) + digits.exponent > AMOUNT_PRECISION - AMOUNT_SCALE:
        raise ValueError("amount exceeds precision")
    return value


def amount_string(value: Decimal | str | None) -> str | None:
    """Return a plain decimal string, preserving numeric value and null."""
    parsed = parse_amount(value)
    if parsed is None:
        return None
    if parsed.is_zero():
        return "0"
    text = format(parsed, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class ExactAmount(TypeDecorator):
    """Protect every live-metadata Core binding, not only append_final callers.

    Frozen migration uses ordinary DECIMAL; application validation cannot
    protect raw SQL which bypasses this binder.
    """
    impl = DECIMAL(AMOUNT_PRECISION, AMOUNT_SCALE)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return amount_string(value)
