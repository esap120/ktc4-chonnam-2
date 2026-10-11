import asyncio
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest
from logging_faults import install_logging_fault

from daesingo.common.logging import (
    bind_context, configure_logging, copy_context_call, log_event, new_trace_id,
)


def test_json_lines_and_nested_context_reset():
    stream = io.StringIO()
    logger = configure_logging("api", stream=stream)
    with bind_context(trace_id=new_trace_id(), case_id="case_1"):
        log_event(logger, "request.started", module="api")
        with bind_context(job_id="job_1", execution_id="exec_1"):
            log_event(logger, "job.execution.completed", duration_ms=2, status="SUCCEEDED")
        log_event(logger, "request.completed")
    log_event(logger, "process.started", revision="test-revision")
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(rows) == 4
    assert rows[0]["trace_id"] == rows[1]["trace_id"]
    assert rows[1]["case_id"] == "case_1"
    assert rows[1]["job_id"] == "job_1" and rows[1]["execution_id"] == "exec_1"
    assert "job_id" not in rows[2] and "case_id" not in rows[3]
    assert rows[1]["duration_ms"] == 2 and rows[1]["status"] == "SUCCEEDED"
    assert rows[3]["service"] == "api" and rows[3]["revision"] == "test-revision"
    assert rows[0]["level"] == "INFO"
    assert rows[0]["timestamp"].endswith("Z")


def test_async_tasks_are_isolated_and_context_is_reset_after_error():
    stream = io.StringIO()
    logger = configure_logging("worker", stream=stream)

    async def task(trace):
        with bind_context(trace_id=trace):
            await asyncio.sleep(0)
            log_event(logger, "task.completed")

    async def run():
        await asyncio.gather(task("tr_a"), task("tr_b"))

    asyncio.run(run())
    with pytest.raises(RuntimeError):
        with bind_context(trace_id="tr_error"):
            raise RuntimeError("secret")
    log_event(logger, "after.error")
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [row.get("trace_id") for row in rows] == ["tr_a", "tr_b", None]


def test_explicit_thread_propagation_captures_context_at_submission():
    stream = io.StringIO()
    logger = configure_logging("worker", stream=stream)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with bind_context(trace_id="tr_parent", execution_id="exec_1"):
            callback = copy_context_call(lambda: log_event(logger, "thread.completed"))
        pool.submit(callback).result()
        pool.submit(lambda: log_event(logger, "thread.clean")).result()
    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert rows[0]["trace_id"] == "tr_parent"
    assert "trace_id" not in rows[1]


def test_event_helper_rejects_payloads_and_formatter_suppresses_raw_messages():
    stream = io.StringIO()
    logger = configure_logging("api", stream=stream)
    with pytest.raises(ValueError):
        log_event(logger, "unsafe.event", payload={"token": "secret"})
    with pytest.raises(ValueError):
        log_event(logger, "unsafe.event", duration_ms=float("nan"))
    with pytest.raises(ValueError):
        log_event(logger, "unsafe event\nsecret")
    try:
        raise RuntimeError("secret /private/file 12가3456")
    except RuntimeError:
        logger.exception("secret raw message", extra={"payload": "secret"})
    row = json.loads(stream.getvalue())
    assert "secret" not in stream.getvalue()
    assert "12가3456" not in stream.getvalue()
    assert "payload" not in row and "message" not in row and "exc_info" not in row


def test_logging_reconfiguration_does_not_duplicate_and_honors_level():
    stream = io.StringIO()
    configure_logging("api", stream=stream)
    logger = configure_logging("api", level="WARNING", stream=stream)
    log_event(logger, "debug.event", level=logging.DEBUG)
    log_event(logger, "warning.event", level=logging.WARNING)
    assert len(stream.getvalue().splitlines()) == 1


def test_trace_ids_are_distinct_opaque_and_do_not_replace_business_ids():
    first, second = new_trace_id(), new_trace_id()
    assert first != second
    assert first.startswith("tr_") and len(first) == 35


def test_context_rejects_unknown_fields():
    with pytest.raises(ValueError):
        with bind_context(api_key="secret"):
            pass


def test_formatter_failure_cannot_expose_raw_message_to_stderr(capsys):
    stream = io.StringIO()
    logger = configure_logging("api", stream=stream)
    logger.error("private-provider-secret", extra={
        "runtime_fields": {"duration_ms": 10 ** 1000},
    })
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "private" not in stream.getvalue()
    assert json.loads(stream.getvalue())["event"] == "log.unstructured"
    with pytest.raises(ValueError):
        log_event(logger, "unsafe.event", duration_ms=10 ** 1000)


def test_transport_failure_reports_only_static_metadata(capsys):
    class BrokenStream(io.StringIO):
        def write(self, value):
            raise OSError("private transport failure")

    logger = configure_logging("api", stream=BrokenStream())
    logger.error("private-provider-secret")
    captured = capsys.readouterr()
    assert "private" not in captured.err
    assert json.loads(captured.err)["event"] == "log.write.failed"


@pytest.mark.parametrize("sink", ["filter", "handler"])
def test_strict_log_event_keeps_existing_sink_exception_contract(sink):
    logger = configure_logging("api", stream=io.StringIO())
    error = ValueError("secret /private/filter")
    seen, remove = install_logging_fault(logger, sink, lambda name: True, error)
    try:
        with pytest.raises(ValueError) as caught:
            log_event(logger, "runtime.test.event")
        assert caught.value is error and seen == ["runtime.test.event"]
    finally:
        remove()


@pytest.mark.parametrize("sink", ["filter", "handler"])
def test_best_effort_isolates_sink_value_error_without_stderr(sink, capsys):
    from daesingo.common import logging as module
    logger = configure_logging("worker", stream=io.StringIO())
    seen, remove = install_logging_fault(logger, sink, lambda name: True)
    try:
        module.log_event_best_effort(logger, "runtime.test.event")
        assert seen == ["runtime.test.event"]
        assert capsys.readouterr().err == ""
    finally:
        remove()


@pytest.mark.parametrize("event,fields", [
    ("unsafe event\nsecret", {}), ("runtime.test.event", {"payload": "secret"}),
    ("runtime.test.event", {"trace_id": "/private/path"}),
    ("runtime.test.event", {"duration_ms": float("nan")}),
    ("runtime.test.event", {"unknown_id": "id"}),
])
def test_best_effort_validates_before_sink_and_does_not_hide_programming_errors(event, fields):
    from daesingo.common import logging as module
    logger = configure_logging("worker", stream=io.StringIO())
    seen, remove = install_logging_fault(logger, "filter", lambda name: True)
    try:
        with pytest.raises(ValueError, match="unsafe operational event"):
            module.log_event_best_effort(logger, event, **fields)
        assert seen == []
    finally:
        remove()


@pytest.mark.parametrize("sink", ["filter", "handler"])
@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(7)])
def test_best_effort_does_not_swallow_base_exceptions(sink, error):
    from daesingo.common import logging as module
    logger = configure_logging("worker", stream=io.StringIO())
    seen, remove = install_logging_fault(logger, sink, lambda name: True, error)
    try:
        with pytest.raises(type(error)) as caught:
            module.log_event_best_effort(logger, "runtime.test.event")
        assert caught.value is error and seen == ["runtime.test.event"]
    finally:
        remove()


def test_best_effort_keeps_structured_context_and_stream_oserror_policy(capsys):
    from daesingo.common import logging as module
    stream = io.StringIO()
    logger = configure_logging("worker", stream=stream)
    with bind_context(trace_id="trace", case_id="case", job_id="job", execution_id="exec"):
        module.log_event_best_effort(logger, "runtime.execution.completed", status="SUCCEEDED")
    row = json.loads(stream.getvalue())
    assert (row["trace_id"], row["case_id"], row["job_id"], row["execution_id"]) == ("trace", "case", "job", "exec")
    assert row["event"] == "runtime.execution.completed" and row["status"] == "SUCCEEDED"

    class BrokenStream(io.StringIO):
        def write(self, value):
            raise OSError("secret /private/transport")

    logger = configure_logging("worker", stream=BrokenStream())
    module.log_event_best_effort(logger, "runtime.test.event")
    assert json.loads(capsys.readouterr().err) == {"level": "ERROR", "event": "log.write.failed"}
