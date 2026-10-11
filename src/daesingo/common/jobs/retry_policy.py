"""Baseline B-L3 and B-R1..3, independent of clocks and persistence."""

from datetime import datetime

from daesingo.common.config import WorkerSettings


def is_stale(status: str, lease_expires_at: datetime | None, now: datetime) -> bool:
    return status == "RUNNING" and lease_expires_at is not None and lease_expires_at < now


def should_retry(status: str, attempt: int, cancelled: bool, *, retry_max: int) -> bool:
    # retry_max counts executions added AFTER attempt 1.
    return status == "STALE" and attempt <= retry_max and not cancelled


def retry_backoff(next_attempt: int, settings: WorkerSettings) -> float:
    if next_attempt < 2:
        raise ValueError("backoff requires a retry attempt")
    delay = min(settings.stale_retry_backoff_base_sec, settings.stale_retry_backoff_max_sec)
    remaining = next_attempt - 2
    # Stop at the cap without constructing huge integers or overflowing powers.
    while remaining and delay < settings.stale_retry_backoff_max_sec:
        delay = min(delay * 2, settings.stale_retry_backoff_max_sec)
        remaining -= 1
    return delay
