"""Lease expiry is the only stale criterion; retry is STALE-only."""

from datetime import datetime, timedelta
from importlib import import_module, util

import pytest

from daesingo.common.config import WorkerSettings


def policy():
    assert util.find_spec("daesingo.common.jobs.retry_policy"), "RT-06 retry policy missing"
    return import_module("daesingo.common.jobs.retry_policy")


@pytest.mark.parametrize("status,delta,want", [
    ("RUNNING", -1, True), ("RUNNING", 0, False), ("RUNNING", 1, False),
    ("FAILED", -1, False), ("QUEUED", -1, False), ("STALE", -1, False),
])
def test_stale_uses_strict_lease_expiry(status, delta, want):
    now = datetime(2026, 10, 11)
    assert policy().is_stale(status, now + timedelta(seconds=delta), now) is want
    assert policy().is_stale(status, None, now) is False


@pytest.mark.parametrize("status,attempt,cancelled,want", [
    ("STALE", 1, False, True), ("STALE", 2, False, False),
    ("STALE", 1, True, False), ("FAILED", 1, False, False),
    ("SUCCEEDED", 1, False, False), ("RUNNING", 1, False, False),
])
def test_retry_only_stale_below_cap_without_marker(status, attempt, cancelled, want):
    assert policy().should_retry(status, attempt, cancelled, retry_max=1) is want
    assert not policy().should_retry("STALE", 1, False, retry_max=0)


@pytest.mark.parametrize("attempt,want", [(2, 5), (3, 10), (4, 20), (5, 40), (6, 60), (10000, 60)])
def test_backoff_is_deterministic_and_capped(attempt, want):
    assert policy().retry_backoff(attempt, WorkerSettings()) == want


def test_backoff_respects_config_and_requires_retry_attempt():
    settings = WorkerSettings(stale_retry_backoff_base_sec=0.25, stale_retry_backoff_max_sec=0.5)
    assert policy().retry_backoff(2, settings) == 0.25
    assert policy().retry_backoff(3, settings) == 0.5
    with pytest.raises(ValueError):
        policy().retry_backoff(1, settings)
