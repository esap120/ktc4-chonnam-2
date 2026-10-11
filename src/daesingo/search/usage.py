from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class UsageLike(Protocol):
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_thought_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int | None
    output_tokens: int | None
    thought_tokens: int | None
    total_tokens: int | None

    @classmethod
    def from_sdk(cls, usage: UsageLike | None) -> "ProviderUsage":
        if usage is None:
            return cls(None, None, None, None)
        return cls(
            input_tokens=usage.total_input_tokens,
            output_tokens=usage.total_output_tokens,
            thought_tokens=usage.total_thought_tokens,
            total_tokens=usage.total_tokens,
        )

    def cost_with_rates(
        self,
        input_usd_per_million: float,
        output_usd_per_million: float,
    ) -> Decimal | None:
        """Return exact Decimal cost using injected per-million-token rates.

        Returns None if any token count is missing (→ BUDGET_UNAVAILABLE upstream).
        두 단가가 모두 0.0(기본값)이면 단가 미설정이라 None이다 — 0원으로 쓰지 않는다(#153).
        """
        if input_usd_per_million == 0.0 and output_usd_per_million == 0.0:
            return None
        if (
            self.input_tokens is None
            or self.output_tokens is None
            or self.thought_tokens is None
        ):
            return None
        in_rate = Decimal(str(input_usd_per_million))
        out_rate = Decimal(str(output_usd_per_million))
        return (
            Decimal(self.input_tokens) * in_rate
            + Decimal(self.output_tokens + self.thought_tokens) * out_rate
        ) / Decimal(1_000_000)
