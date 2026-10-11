from dataclasses import FrozenInstanceError
from pathlib import Path
import re

import pytest

from daesingo.common.config import ConfigError, RuntimeConfig, runtime_keys


PREFIX = "DAESINGO_RUNTIME_"


def required(service="api"):
    return {
        PREFIX + "DB_URL": "mysql+pymysql://test:test@localhost/test_runtime",
        PREFIX + "MEDIA_ROOT": "/runtime/media",
        PREFIX + service.upper() + "_TEMP_ROOT": f"/runtime/{service}-temp",
    }


@pytest.mark.parametrize("service,pool", [("api", 5), ("worker", 2)])
def test_baseline_db_and_common_defaults(service, pool):
    config = RuntimeConfig.from_mapping(service, required(service))
    assert (config.db.pool_size, config.db.max_overflow) == (pool, pool)
    assert (config.db.lock_wait_timeout_sec, config.db.pool_timeout_sec) == (5, 5)
    assert config.db.pool_recycle_sec == 1800
    assert config.db.pool_pre_ping is True
    assert (config.db.connect_timeout_sec, config.db.read_timeout_sec,
            config.db.write_timeout_sec) == (5, 30, 30)
    assert (config.cleanup.temp_age_sec, config.cleanup.interval_sec) == (3600, 3600)
    assert config.log_level == "INFO"
    assert config.service == service


def test_baseline_api_defaults_and_service_schema():
    config = RuntimeConfig.from_mapping("api", required())
    assert config.worker is None and config.heartbeat is None
    assert (config.upload.max_bytes, config.upload.json_max_bytes) == (1073741824, 1048576)
    assert (config.upload.idle_timeout_sec, config.upload.max_duration_sec) == (60, 1800)
    assert (config.frame.max_age_sec, config.frame.concurrency) == (3600, 2)
    assert (config.cleanup.staging_age_sec, config.cleanup.orphan_age_sec) == (3600, 86400)
    assert (config.ready.db_timeout_sec, config.ready.storage_timeout_sec,
            config.ready.budget_sec) == (2, 1, 3)
    # Worker-only settings, even malformed, do not become API requirements.
    env = required() | {PREFIX + "HEARTBEAT_INTERVAL_SEC": "invalid"}
    assert RuntimeConfig.from_mapping("api", env).heartbeat is None


def test_baseline_worker_defaults_and_service_schema():
    config = RuntimeConfig.from_mapping("worker", required("worker"))
    assert config.upload is None and config.frame is None and config.ready is None
    assert config.cleanup.staging_age_sec is None and config.cleanup.orphan_age_sec is None
    assert (config.worker.idle_poll_sec, config.worker.error_backoff_sec) == (2, 5)
    assert (config.worker.heartbeat_interval_sec, config.worker.lease_duration_sec,
            config.worker.stale_sweep_interval_sec) == (10, 60, 15)
    assert (config.worker.stale_retry_max, config.worker.stale_retry_backoff_base_sec,
            config.worker.stale_retry_backoff_max_sec) == (1, 5, 60)
    assert (config.heartbeat.connect_timeout_sec, config.heartbeat.read_timeout_sec,
            config.heartbeat.write_timeout_sec, config.heartbeat.lock_wait_timeout_sec) == (2, 5, 5, 2)
    # B-D9: phase timeout sums do not impose a heartbeat deadline (2+5+5 > 10).
    assert sum((config.heartbeat.connect_timeout_sec, config.heartbeat.read_timeout_sec,
                config.heartbeat.write_timeout_sec)) > config.worker.heartbeat_interval_sec
    assert not hasattr(config.worker, "concurrency")


@pytest.mark.parametrize("service", ["api", "worker"])
def test_runtime_config_is_deeply_immutable_and_does_not_expose_secrets(service):
    config = RuntimeConfig.from_mapping(service, required(service))
    for obj, field in [(config, "service"), (config.db, "pool_size"),
                       (config.cleanup, "interval_sec")]:
        with pytest.raises((FrozenInstanceError, AttributeError, ValueError)):
            setattr(obj, field, 999)
    assert "test:test" not in repr(config)
    assert "/runtime/media" not in repr(config)


@pytest.mark.parametrize("service,suffix,value", [
    ("worker", "HEARTBEAT_INTERVAL_SEC", "0"),
    ("worker", "HEARTBEAT_INTERVAL_SEC", "NaN"),
    ("worker", "LEASE_DURATION_SEC", "10"),
    ("worker", "STALE_SWEEP_INTERVAL_SEC", "-1"),
    ("worker", "HEARTBEAT_DB_CONNECT_TIMEOUT_SEC", "0"),
    ("worker", "HEARTBEAT_DB_READ_TIMEOUT_SEC", "2"),
    ("worker", "HEARTBEAT_DB_WRITE_TIMEOUT_SEC", "0"),
    ("worker", "DB_LOCK_WAIT_TIMEOUT_SEC", "10"),
    ("api", "CLEANUP_STAGING_AGE_SEC", "3599"),
    ("api", "READY_DB_TIMEOUT_SEC", "2.1"),
    ("api", "READY_STORAGE_TIMEOUT_SEC", "1.1"),
    ("api", "DB_POOL_SIZE", "0"),
    ("api", "DB_MAX_OVERFLOW", "-1"),
    ("api", "DB_CONNECT_TIMEOUT_SEC", "0"),
    ("api", "DB_READ_TIMEOUT_SEC", "inf"),
    ("api", "DB_WRITE_TIMEOUT_SEC", "-1"),
    ("api", "DB_POOL_TIMEOUT_SEC", "0"),
    ("api", "DB_POOL_RECYCLE_SEC", "0"),
    ("api", "API_UPLOAD_MAX_BYTES", "0"),
    ("api", "API_JSON_MAX_BYTES", "-1"),
    ("api", "API_UPLOAD_IDLE_TIMEOUT_SEC", "0"),
    ("api", "API_UPLOAD_MAX_DURATION_SEC", "0"),
    ("api", "API_FRAME_CONCURRENCY", "0"),
    ("api", "API_FRAME_MAX_AGE_SEC", "-1"),
    ("api", "CLEANUP_ORPHAN_AGE_SEC", "0"),
    ("api", "CLEANUP_TEMP_AGE_SEC", "0"),
    ("api", "CLEANUP_INTERVAL_SEC", "0"),
    ("worker", "STALE_RETRY_MAX", "-1"),
    ("worker", "STALE_RETRY_BACKOFF_BASE_SEC", "0"),
    ("worker", "BACKOFF_MAX_SEC", "0"),
    ("worker", "WORKER_IDLE_POLL_SEC", "0"),
    ("worker", "WORKER_ERROR_BACKOFF_SEC", "0"),
    ("api", "LOG_LEVEL", "secret-invalid-level"),
    ("api", "DB_URL", "secret-invalid-url"),
    ("api", "MEDIA_ROOT", ""),
    ("api", "API_TEMP_ROOT", ""),
])
def test_invalid_ranges_and_baseline_invariants_report_only_keys(service, suffix, value):
    key = PREFIX + suffix
    with pytest.raises(ConfigError) as error:
        RuntimeConfig.from_mapping(service, required(service) | {key: value})
    assert key in error.value.keys
    assert all(name.startswith(PREFIX) for name in str(error.value).split(", "))


@pytest.mark.parametrize("service", ["api", "worker"])
def test_required_keys_have_no_invented_defaults(service):
    for key in required(service):
        env = required(service)
        del env[key]
        with pytest.raises(ConfigError) as error:
            RuntimeConfig.from_mapping(service, env)
        assert key in error.value.keys


def test_key_registry_has_only_baseline_knobs_and_documented_extra_keys():
    assert PREFIX + "DB_POOL_SIZE" in runtime_keys()
    assert PREFIX + "BACKOFF_MAX_SEC" in runtime_keys()
    assert PREFIX + "WORKER_CONCURRENCY" not in runtime_keys()
    assert PREFIX + "READY_BUDGET_SEC" not in runtime_keys()
    assert PREFIX + "HEARTBEAT_DB_LOCK_WAIT_TIMEOUT_SEC" not in runtime_keys()


def test_key_registry_matches_canonical_baseline_candidates():
    baseline = Path(__file__).resolve().parents[3] / "docs/runtime/provisional-baseline-v0.1.md"
    section = baseline.read_text(encoding="utf-8").split("## 2. Baseline", 1)[1].split("## 3.", 1)[0]
    candidates = set()
    for line in section.splitlines():
        if line.startswith("| B-"):
            scope = line.split("|")[4]
            for token in re.findall(r"`([^`]+)`", scope):
                if token.startswith(PREFIX):
                    candidates.add(token)
                elif token.startswith("…_"):
                    candidates.add(PREFIX + token[2:])
    extra = {PREFIX + suffix for suffix in ("DB_URL", "MEDIA_ROOT", "API_TEMP_ROOT", "WORKER_TEMP_ROOT")}
    assert runtime_keys() == candidates | extra


def test_unknown_key_does_not_prevent_config_creation():
    assert RuntimeConfig.from_mapping("api", required() | {PREFIX + "FUTURE": "secret"})


def test_nonnegative_settings_and_fractional_intervals_are_allowed():
    config = RuntimeConfig.from_mapping("worker", required("worker") | {
        PREFIX + "DB_MAX_OVERFLOW": "0", PREFIX + "STALE_RETRY_MAX": "0",
        PREFIX + "WORKER_IDLE_POLL_SEC": "0.25",
    })
    assert config.db.max_overflow == config.worker.stale_retry_max == 0
    assert config.worker.idle_poll_sec == 0.25
