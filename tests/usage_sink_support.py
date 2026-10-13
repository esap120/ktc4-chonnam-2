"""Shared fake invocation facts; no real provider or Search dependency."""

from importlib import import_module

import sqlalchemy as sa


def mod():
    return import_module("daesingo.common.usage.sink")


def facts(**changes):
    return {**dict(token_usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        processed_duration_sec=4.5, latency_ms=17, pricing_context={"pricing_id": "price", "unit": "opaque"},
        cost={"amount": "1.20", "currency": "KRW"}, outcome="SUCCEEDED"), **changes}


def begin(sink, **kwargs):
    return sink.begin("SEARCH_COARSE", "fake", {"pricing_id": "price", "unit": "opaque"}, **kwargs)


def rows(engine):
    from daesingo.common.usage.schema import usage_inflight, usage_record
    with engine.connect() as conn:
        return ([dict(r) for r in conn.execute(sa.select(usage_inflight)).mappings()],
                [dict(r) for r in conn.execute(sa.select(usage_record)).mappings()])


def finalize(sink, identity, run="run"):
    sink.finalize(identity, run_ref={"kind": "analysis_run", "ref": run} if run else None,
                  run_ref_reason=None if run else "RUN_NOT_PRODUCED")
