"""Real Case fixtures and spawned Worker entry point for RT-06(b)."""

from io import StringIO
from threading import Event
from types import MappingProxyType
import importlib

from sqlalchemy import select

from daesingo.case import command, service
from daesingo.case.store import CaseStore
from daesingo.case.store_mysql import MySQLCaseRepository
from daesingo.case.timeline_source import CaseTimeline
from daesingo.common.bootstrap import Startup
from daesingo.common.config import RuntimeConfig
from daesingo.common.db import create_worker_engine
from daesingo.common.jobs.execution import HandlerResult
from daesingo.common.jobs.read_port import read_executions
from daesingo.common.jobs.repository import enqueue, claim_one, finish
from daesingo.common.jobs.schema import job_execution as jobs
from daesingo.common.logging import configure_logging
from daesingo.worker.composition import compose_worker
from daesingo.worker.registry import KindRegistry


class Timelines:
    def timeline_for(self, sources):
        return CaseTimeline("tl_redelivery", 1, 10000)


def reader(conn, kind, produced):
    if kind == "HINT_EXTRACT":
        return {"status": "ABSTAINED"}
    return {"outcome": "SUCCEEDED", "candidate_events": [{
        "candidate_id": "candidate_redelivery", "summary": "test", "thumbnail_ref": "frame_test",
        "rank": 1, "span": {"representative_ms": 4000, "timeline_revision": 1}}]}


def store(conn):
    return CaseStore(repository=MySQLCaseRepository(), conn=conn, executions=read_executions)


def adapter(**kwargs):
    module = importlib.import_module("daesingo.worker.case_reflector")
    return module.CaseReflector(reader=reader, timelines=Timelines(), **kwargs)


def config(url):
    return RuntimeConfig.from_mapping("worker", {
        "DAESINGO_RUNTIME_DB_URL": url,
        "DAESINGO_RUNTIME_MEDIA_ROOT": "/test/media",
        "DAESINGO_RUNTIME_WORKER_TEMP_ROOT": "/test/temp",
        "DAESINGO_RUNTIME_DB_LOCK_WAIT_TIMEOUT_SEC": "1",
        "DAESINGO_RUNTIME_HEARTBEAT_INTERVAL_SEC": "2",
        "DAESINGO_RUNTIME_LEASE_DURATION_SEC": "3",
        "DAESINGO_RUNTIME_STALE_SWEEP_INTERVAL_SEC": "0.05",
        "DAESINGO_RUNTIME_STALE_RETRY_BACKOFF_BASE_SEC": "0.1",
    })


def seed(engine, *, description="", terminal=True, status="SUCCEEDED", attempt=1):
    with engine.begin() as conn:
        case_id = service.create_case(store=store(conn))
        service.record_source_registered(case_id,
            {"source_asset_ref": "asset_test", "availability": "AVAILABLE", "duration_sec": 10.0},
            media_streams=[{"media_stream_ref": "stream_test", "media_type": "VIDEO"}], store=store(conn))
        result = command.execute_command({"case_id": case_id, "expected_case_rev": 1,
            "kind": "START_ANALYSIS", "payload": {"description": description}},
            store=store(conn), timelines=Timelines())
        execution_id, = enqueue(conn, result.appended_job_records, "trace_redelivery")
        if attempt != 1:
            conn.execute(jobs.update().where(jobs.c.execution_id == execution_id).values(attempt=attempt))
    if terminal:
        claimed = claim_one(engine, "seed_owner", lease_duration_sec=3)
        assert claimed.execution_id == execution_id
        with engine.begin() as conn:
            assert finish(conn, execution_id, "seed_owner", status=status,
                failure_kind="TEST_FAILED" if status == "FAILED" else None) == 1
    return case_id, execution_id


def row(engine, execution_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(jobs).where(jobs.c.execution_id == execution_id)).mappings().one())


def snapshot(engine, case_id):
    with engine.begin() as conn:
        return store(conn).get_case(case_id)


def spawned_worker(url, mode, pipe):
    """Child owns every engine/thread. IPC pins the kill boundary, never sleep."""
    cfg = config(url)
    engine = create_worker_engine(cfg.db)
    stop = Event()
    logger = configure_logging("worker", stream=StringIO())
    startup = Startup(cfg, MappingProxyType({}), logger)

    def handler(context):
        if mode == "running":
            pipe.send(("RUNNING", context.execution_id))
            pipe.recv()  # Parent kills this process with an active heartbeat.
        stop.set()
        return HandlerResult()

    loop = compose_worker(engine=engine, startup=startup, stop=stop,
        registry=KindRegistry({"HINT_EXTRACT": handler, "COARSE_SEARCH": handler}),
        reflector=adapter())
    if mode == "gap":
        original = loop.reflect

        def gap(context, terminal):
            pipe.send(("T1", context.execution_id))
            pipe.recv()  # Durable T1, no T2 entry yet.
            return original(context, terminal)
        loop.reflect = gap
    try:
        loop.run()
        pipe.send(("DONE", None))
    finally:
        engine.dispose()
        pipe.close()
