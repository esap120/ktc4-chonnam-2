"""JSON line operational events with explicit, minimal metadata.

Never pass free text, paths, provider payloads, or secrets as identifiers.
This is a safe event API, not a global third-party masking logger.
"""

import contextvars
import hashlib
import json
import logging
import math
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import partial
from typing import TextIO
from uuid import uuid4

_CONTEXT_FIELDS = frozenset({"trace_id", "case_id", "job_id", "execution_id", "module"})
_TOKEN_FIELDS = _CONTEXT_FIELDS | {"status", "revision"}
_TOKEN = re.compile(r"[A-Za-z0-9_.:@+-]{1,128}\Z")
_JOB_TOKEN = re.compile(r"[A-Za-z0-9_.:@+-]{1,191}\Z")
_EVENT = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z")
_KEY = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_context = contextvars.ContextVar("runtime_correlation", default=None)


def new_trace_id() -> str:
    return "tr_" + uuid4().hex


def _validate(fields):
    for name, value in fields.items():
        if name in _TOKEN_FIELDS:
            pattern = _JOB_TOKEN if name == "job_id" else _TOKEN
            valid = isinstance(value, str) and pattern.fullmatch(value)
        elif name == "duration_ms":
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
            except OverflowError:
                valid = False
        elif name == "keys":
            valid = isinstance(value, (list, tuple)) and all(
                isinstance(key, str) and _KEY.fullmatch(key) for key in value
            )
        else:
            valid = False
        if not valid:
            raise ValueError("unsafe operational event field")


def safe_correlation(**fields: str) -> dict[str, str]:
    """Keep trusted IDs; use stable opaque aliases for non-token storage IDs.

    Queue identity storage permits ASCII paths/control characters. They must
    neither break dispatch through log validation nor appear verbatim in logs.
    This does not identify secrets in arbitrary strings: callers supply IDs only.
    """
    if fields.keys() - _CONTEXT_FIELDS:
        raise ValueError("unknown correlation field")
    return {name: value if (_JOB_TOKEN if name == "job_id" else _TOKEN).fullmatch(value)
            else "id_" + hashlib.sha256(value.encode("utf-8")).hexdigest()
            for name, value in fields.items()}


@contextmanager
def bind_context(**fields) -> Iterator[None]:
    if fields.keys() - _CONTEXT_FIELDS:
        raise ValueError("unknown correlation field")
    _validate(fields)
    token = _context.set((_context.get() or {}) | fields)
    try:
        yield
    finally:
        _context.reset(token)


def copy_context_call(callback: Callable, /, *args, **kwargs) -> Callable:
    """Capture at submission; use once for each thread/executor submission."""
    context = contextvars.copy_context()
    return partial(context.run, callback, *args, **kwargs)


class _JsonFormatter(logging.Formatter):
    def __init__(self, service):
        super().__init__()
        self.service = service

    def format(self, record):
        # Ignore raw message, args, exception text, stack info and arbitrary extras.
        fields = getattr(record, "runtime_fields", {})
        event = getattr(record, "runtime_event", "log.unstructured")
        try:
            _validate(fields)
            if not isinstance(event, str) or not _EVENT.fullmatch(event):
                raise ValueError("unsafe operational event")
        except (ValueError, TypeError, AttributeError, OverflowError):
            fields, event = {}, "log.unstructured"
        return json.dumps({
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname, "service": self.service, "event": event, **fields,
        }, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class _SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record):
        # stdlib diagnostics include raw message/args and exception text.
        # A broken output stream must not turn those into a disclosure.
        try:
            sys.stderr.write('{"level":"ERROR","event":"log.write.failed"}\n')
        except (OSError, ValueError):
            pass


def configure_logging(service: str, *, level: str = "INFO", stream: TextIO | None = None) -> logging.Logger:
    """Dedicated logger; no root/third-party handlers are modified."""
    if service not in ("api", "worker") or level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ValueError("invalid runtime logging configuration")
    logger = logging.getLogger("daesingo.runtime." + service)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = _SafeStreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(_JsonFormatter(service))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


def _event_metadata(event, fields):
    if not isinstance(event, str) or not _EVENT.fullmatch(event):
        raise ValueError("unsafe operational event name")
    merged = (_context.get() or {}) | fields
    _validate(merged)
    return {"runtime_event": event, "runtime_fields": merged}


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields) -> None:
    metadata = _event_metadata(event, fields)
    logger.log(level, "", extra=metadata)


def log_event_best_effort(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields) -> None:
    """Validate strictly; isolate ordinary sink failures for opted-in callers.

    Validation errors remain programming errors. Filters/handlers may raise the
    same exception types, so isolate only the sink call, never validation.
    Like transaction _emit/observer, catch Exception, without stderr diagnostics.
    The existing log_event API and other callers retain their strict behavior.
    """
    metadata = _event_metadata(event, fields)
    try:
        logger.log(level, "", extra=metadata)
    except Exception:
        pass


__all__ = ["bind_context", "configure_logging", "copy_context_call", "log_event", "log_event_best_effort",
           "new_trace_id", "safe_correlation"]
