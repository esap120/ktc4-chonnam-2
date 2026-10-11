"""Immutable, file-mapping-only Runtime configuration (Baseline v0.1).

No environment access, DB connections, or module/provider semantics live here.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

PREFIX = "DAESINGO_RUNTIME_"
PositiveSeconds = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonnegativeInt = Annotated[int, Field(ge=0)]


class ConfigError(ValueError):
    """Only trusted key names; never retain raw input or validation exceptions."""

    def __init__(self, keys: tuple[str, ...] | list[str]):
        self.keys = tuple(sorted(set(keys)))
        super().__init__(", ".join(self.keys))


class _Settings(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", allow_inf_nan=False,
        hide_input_in_errors=True, validate_default=True,
    )
    key_prefix: ClassVar[str]

    @classmethod
    def key(cls, name: str) -> str:
        return PREFIX + cls.key_prefix + name.upper()


class DbSettings(_Settings):
    """RT-02 interface: URL via url.get_secret_value(); no engine is created."""

    key_prefix = "DB_"
    url: SecretStr
    pool_size: PositiveInt = 5
    max_overflow: NonnegativeInt = 5
    lock_wait_timeout_sec: PositiveInt = 5
    pool_timeout_sec: PositiveSeconds = 5
    pool_recycle_sec: PositiveInt = 1800
    connect_timeout_sec: PositiveInt = 5
    read_timeout_sec: PositiveSeconds = 30
    write_timeout_sec: PositiveSeconds = 30
    pool_pre_ping: ClassVar[bool] = True  # B-D6: not a knob.

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: SecretStr) -> SecretStr:
        try:
            parsed = make_url(value.get_secret_value())
            valid = (parsed.drivername == "mysql+pymysql" and parsed.host
                     and parsed.database and parsed.username)
            if parsed.port is not None and not 0 < parsed.port <= 65535:
                valid = False
        except (ArgumentError, ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError("invalid DB URL")
        return value


class HeartbeatSettings(_Settings):
    key_prefix = "HEARTBEAT_DB_"
    connect_timeout_sec: PositiveInt = 2
    read_timeout_sec: PositiveSeconds = 5
    write_timeout_sec: PositiveSeconds = 5
    lock_wait_timeout_sec: ClassVar[int] = 2  # B-D9 has no key for this.


class WorkerSettings(_Settings):
    key_prefix = ""
    idle_poll_sec: PositiveSeconds = Field(default=2)
    error_backoff_sec: PositiveSeconds = Field(default=5)
    heartbeat_interval_sec: PositiveSeconds = 10
    lease_duration_sec: PositiveSeconds = 60
    stale_sweep_interval_sec: PositiveSeconds = 15
    stale_retry_max: NonnegativeInt = 1
    stale_retry_backoff_base_sec: PositiveSeconds = 5
    stale_retry_backoff_max_sec: PositiveSeconds = 60

    @classmethod
    def key(cls, name: str) -> str:
        if name in ("idle_poll_sec", "error_backoff_sec"):
            return PREFIX + "WORKER_" + name.upper()
        if name == "stale_retry_backoff_max_sec":
            return PREFIX + "BACKOFF_MAX_SEC"  # Literal B-R2 candidate (Plan P-8).
        return super().key(name)


class UploadSettings(_Settings):
    key_prefix = "API_"
    max_bytes: PositiveInt = 1073741824
    json_max_bytes: PositiveInt = 1048576
    idle_timeout_sec: PositiveSeconds = 60
    max_duration_sec: PositiveSeconds = 1800

    @classmethod
    def key(cls, name: str) -> str:
        return PREFIX + "API_" + (name.upper() if name == "json_max_bytes" else "UPLOAD_" + name.upper())


class FrameSettings(_Settings):
    key_prefix = "API_FRAME_"
    max_age_sec: NonnegativeInt = 3600
    concurrency: PositiveInt = 2


class CleanupSettings(_Settings):
    key_prefix = "CLEANUP_"
    temp_age_sec: PositiveSeconds = 3600
    interval_sec: PositiveSeconds = 3600
    staging_age_sec: PositiveSeconds | None = None
    orphan_age_sec: PositiveSeconds | None = None


class ReadySettings(_Settings):
    key_prefix = "READY_"
    db_timeout_sec: PositiveSeconds = 2
    storage_timeout_sec: PositiveSeconds = 1
    budget_sec: ClassVar[int] = 3  # B-H3: no separate key.


class _LogSettings(_Settings):
    key_prefix = ""
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


_GROUPS = (DbSettings, HeartbeatSettings, WorkerSettings, UploadSettings,
           FrameSettings, CleanupSettings, ReadySettings, _LogSettings)
_PATH_KEYS = (PREFIX + "MEDIA_ROOT", PREFIX + "API_TEMP_ROOT", PREFIX + "WORKER_TEMP_ROOT")


def runtime_keys() -> frozenset[str]:
    """Both service schemas; keys belonging to the other service are known."""
    return frozenset(_PATH_KEYS) | frozenset(
        group.key(name) for group in _GROUPS for name in group.model_fields
    )


def _read(group, values, errors, *, defaults=None, exclude=()):
    selected = dict(defaults or {})
    for name in group.model_fields:
        key = group.key(name)
        if name not in exclude and key in values:
            selected[name] = values[key]
    try:
        return group.model_validate(selected)
    except ValidationError as error:
        errors.extend(group.key(item["loc"][0]) for item in error.errors(
            include_input=False, include_context=False, include_url=False,
        ))
        return None


def _path(values, key, errors):
    value = values.get(key, "")
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        errors.append(key)
        return None
    return Path(value)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    service: Literal["api", "worker"]
    db: DbSettings
    media_root: Path = field(repr=False)
    temp_root: Path = field(repr=False)
    cleanup: CleanupSettings
    log_level: str
    worker: WorkerSettings | None = None
    heartbeat: HeartbeatSettings | None = None
    upload: UploadSettings | None = None
    frame: FrameSettings | None = None
    ready: ReadySettings | None = None

    @classmethod
    def from_mapping(cls, service: Literal["api", "worker"], values: Mapping[str, str]) -> "RuntimeConfig":
        if service not in ("api", "worker"):
            raise ValueError("unsupported runtime service")
        errors = []
        db = _read(DbSettings, values, errors, defaults=(
            {"pool_size": 2, "max_overflow": 2} if service == "worker" else None
        ))
        media_root = _path(values, PREFIX + "MEDIA_ROOT", errors)
        temp_root = _path(values, PREFIX + service.upper() + "_TEMP_ROOT", errors)
        cleanup = _read(CleanupSettings, values, errors,
                        defaults={"staging_age_sec": 3600, "orphan_age_sec": 86400} if service == "api" else None,
                        exclude=("staging_age_sec", "orphan_age_sec") if service == "worker" else ())
        log = _read(_LogSettings, values, errors)
        worker = heartbeat = upload = frame = ready = None
        if service == "worker":
            worker = _read(WorkerSettings, values, errors)
            heartbeat = _read(HeartbeatSettings, values, errors)
            if worker and worker.lease_duration_sec <= worker.heartbeat_interval_sec:
                errors.extend((WorkerSettings.key("lease_duration_sec"), WorkerSettings.key("heartbeat_interval_sec")))
            if db and worker and db.lock_wait_timeout_sec >= worker.heartbeat_interval_sec:
                errors.extend((DbSettings.key("lock_wait_timeout_sec"), WorkerSettings.key("heartbeat_interval_sec")))
            if heartbeat and heartbeat.lock_wait_timeout_sec >= heartbeat.read_timeout_sec:
                errors.append(HeartbeatSettings.key("read_timeout_sec"))
        else:
            upload = _read(UploadSettings, values, errors)
            frame = _read(FrameSettings, values, errors)
            ready = _read(ReadySettings, values, errors)
            if cleanup and upload and cleanup.staging_age_sec < 2 * upload.max_duration_sec:
                errors.extend((CleanupSettings.key("staging_age_sec"), UploadSettings.key("max_duration_sec")))
            if ready and ready.db_timeout_sec + ready.storage_timeout_sec > ready.budget_sec:
                errors.extend((ReadySettings.key("db_timeout_sec"), ReadySettings.key("storage_timeout_sec")))
        if errors:
            raise ConfigError(errors) from None
        return cls(service, db, media_root, temp_root, cleanup, log.log_level,
                   worker, heartbeat, upload, frame, ready)


__all__ = ["ConfigError", "DbSettings", "RuntimeConfig", "runtime_keys"]
