"""Elice 크레딧 단가(KRW / 1M 토큰). 사용자가 Elice 모델 카드에서 직접 확인해 알려준 값
(2026-09-18 확인). 캐시 히트 단가는 무시하고 항상 일반 입력 단가로 계산한다
— 실제보다 비용을 과소평가하지 않는 쪽(안전한 쪽)으로 어림잡기 위함.

JUDGE_MODEL이 이 표에 없는 모델이면 cost는 None으로 나온다(집계에서 "-"로 표시,
조용히 0으로 세지 않음).
"""

from __future__ import annotations

KRW_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "gpt-5-nano": {"input": 76, "output": 609},
    "gemini-3.1-flash-lite": {"input": 380, "output": 2283},
    "claude-haiku-4-5": {"input": 1522, "output": 7612},
    # 2026-10-05 Elice 모델 카드 확인(유소연). 캐시 입력 ₩114는 위 방침대로 쓰지 않는다.
    "gemini-3.8-flash": {"input": 1141, "output": 5709},
    # #281 challenger(2026-10-06 Elice 모델 카드, 이슈 본문).
    "gpt-6-luna": {"input": 152, "output": 761},
    # judge 모델(2026-10-04 Elice 모델 카드 확인). 이전엔 표에 없어 judge 비용이 기록되지 않았다.
    "anthropic/claude-sonnet-5": {"input": 3045, "output": 15225},
    "anthropic/claude-opus-5": {"input": 7612, "output": 38062},
}


def estimate_cost_krw(
    model_name: str, prompt_tokens: int | None, completion_tokens: int | None
) -> float | None:
    rates = KRW_PER_1M_TOKENS.get(model_name)
    if rates is None or prompt_tokens is None or completion_tokens is None:
        return None
    return (prompt_tokens / 1_000_000) * rates["input"] + (
        completion_tokens / 1_000_000
    ) * rates["output"]
