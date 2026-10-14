"""Fake provider + real durable Runtime facts; no Search/provider dependencies."""

from datetime import datetime, timedelta
from importlib import import_module

import sqlalchemy as sa

from daesingo.common.db.transactions import run_worker_transaction
from daesingo.common.jobs.schema import job_execution as jobs
from usage_sink_support import facts, rows

RUN = {"kind": "analysis_run", "ref": "actual_run"}


def module():
    return import_module("daesingo.common.usage.reconciliation")


def sink(engine, execution="exec", *, transaction=None, **kwargs):
    from daesingo.common.usage.sink import DurableUsageSink
    return DurableUsageSink(execution_ref=execution, case_id="case",
        transaction=transaction or (lambda cb: run_worker_transaction(engine, cb, sleep=lambda _: None)),
        **kwargs)


def job(engine, status="STALE", *, execution="exec", produced=(), case_id="case"):
    with engine.begin() as conn:
        now = conn.scalar(sa.select(sa.func.now(6)))
        conn.execute(jobs.insert().values(execution_id=execution, job_id="job_" + execution,
            case_id=case_id, kind="COARSE_SEARCH", trace_id="trace", attempt=1,
            status=status, produced=list(produced), queued_at=now - timedelta(seconds=5),
            available_at=now - timedelta(seconds=5), started_at=None if status == "QUEUED" else now - timedelta(seconds=4),
            ended_at=None if status in ("RUNNING", "QUEUED") else now,
            failure_kind="FAKE" if status == "FAILED" else None,
            lease_owner="worker", lease_expires_at=now + timedelta(seconds=60)))


def begin(s, *, run=RUN, reason=None):
    return s.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"},
        run_ref=run, run_ref_reason=reason)


def reconcile(engine, **kwargs):
    return module().reconcile_once(engine, sleep=lambda _: None, **kwargs)


class BrokenLogger:
    def log(self, *args, **kwargs):
        raise RuntimeError("raw SQL secret /private/db")


def broken_observer(_):
    raise RuntimeError("raw SQL secret /private/observer")


def worker_config(url):
    from daesingo.common.config import RuntimeConfig
    return RuntimeConfig.from_mapping("worker", {
        "DAESINGO_RUNTIME_DB_URL": url,
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/test/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/test/temp",
        "DAESINGO_RUNTIME_DB_LOCK_WAIT_TIMEOUT_SEC": "1",
        "DAESINGO_RUNTIME_HEARTBEAT_INTERVAL_SEC": "2",
        "DAESINGO_RUNTIME_LEASE_DURATION_SEC": "3",
        "DAESINGO_RUNTIME_STALE_SWEEP_INTERVAL_SEC": "0.05",
        "DAESINGO_RUNTIME_STALE_RETRY_MAX": "0",
    })


def worker(engine, cfg, stop, handler=None, hooks=()):
    from io import StringIO
    from types import MappingProxyType
    from daesingo.common.bootstrap import Startup
    from daesingo.common.logging import configure_logging
    from daesingo.worker.composition import compose_worker
    from daesingo.worker.registry import KindRegistry
    return compose_worker(engine=engine, startup=Startup(cfg, MappingProxyType({}),
        configure_logging("worker", stream=StringIO())), stop=stop,
        registry=KindRegistry({"COARSE_SEARCH": handler} if handler else {}),
        sweep_hooks=hooks)


def spawned_usage_worker(url, pipe):
    from threading import Event
    from daesingo.common.db import create_worker_engine
    cfg = worker_config(url)
    engine = create_worker_engine(cfg.db)
    stop = Event()
    calls = []
    def handler(context):
        identity = begin(context.usage_sink)
        calls.append(identity)  # provider is fake and outside any DB callback
        context.usage_sink.finish(identity, **facts())
        pipe.send(("OBSERVED", context.execution_id, identity, len(calls)))
        pipe.recv()  # parent kills after durable finish, before T1/Run relation
        raise AssertionError("parent must kill this worker")
    try:
        worker(engine, cfg, stop, handler).run()
    finally:
        engine.dispose()
        pipe.close()
