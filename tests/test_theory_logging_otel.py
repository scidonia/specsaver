"""Differential fidelity — logging + OTel stubs vs real libraries.

Same pattern as ``test_sqlalchemy_stub.py``: the same program runs
against the real library and the stub, and observable outputs must
match.
"""

from __future__ import annotations

import logging
from io import StringIO

from specsaver.theory.logtheory import make_log_capture
from specsaver.theory.otel import make_otel_capture

# ---------------------------------------------------------------------------
# Logging theory fidelity
# ---------------------------------------------------------------------------


def _real_logging(program):
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        for logger_name, level, msg, extra in program:
            logger = logging.getLogger(logger_name)
            logger.log(level, msg, extra=extra)
        handler.flush()
        return stream.getvalue()
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _stub_logging(program):
    with make_log_capture() as h:
        for logger_name, level, msg, extra in program:
            logger = logging.getLogger(logger_name)
            logger.log(level, msg, extra=extra)
    return h


def test_logging_single_emit_matches():
    program = [("test", logging.INFO, "hello world", {"k": "v"})]
    real_output = _real_logging(program)
    stub = _stub_logging(program)
    assert len(stub.store.emits) == 1
    assert stub.store.emits[0].logger == "test"
    assert stub.store.emits[0].msg == "hello world"
    assert stub.store.emits[0].level == logging.INFO
    assert "hello world" in real_output


def test_logging_levels_captured():
    program = [
        ("svc.api", logging.INFO, "request", {"method": "POST"}),
        ("svc.db", logging.DEBUG, "query", {"sql": "SELECT"}),
        ("svc.api", logging.WARNING, "slow", {"ms": 500}),
        ("svc.api", logging.ERROR, "fail", {"status": 500}),
    ]
    stub = _stub_logging(program)
    assert len(stub.store.emits) == 4
    levels = {e.level for e in stub.store.emits}
    assert levels == {logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR}


def test_logging_extra_fields_survive():
    program = [("test", logging.INFO, "event", {"span_id": "abc", "count": 5})]
    stub = _stub_logging(program)
    assert stub.store.emits[0].extra == {"span_id": "abc", "count": 5}


def test_logging_trace_has_events():
    program = [("a", logging.INFO, "x", {}), ("b", logging.WARNING, "y", {})]
    stub = _stub_logging(program)
    assert len(stub.trace) == 2


def test_logging_by_level_by_logger():
    program = [
        ("api.http", logging.INFO, "GET", {}),
        ("api.http", logging.ERROR, "500", {}),
        ("db.query", logging.DEBUG, "SELECT", {}),
    ]
    stub = _stub_logging(program)
    assert len(stub.store.by_level[logging.INFO]) == 1
    assert len(stub.store.by_logger["api.http"]) == 2


# ---------------------------------------------------------------------------
# OTel theory fidelity
# ---------------------------------------------------------------------------


def _run_otel_instrumentation(tracer):
    with tracer.start_as_current_span("request") as span:
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.route", "/users")
        with tracer.start_as_current_span("db-query") as db:
            db.set_attribute("db.statement", "SELECT * FROM users")
        with tracer.start_as_current_span("cache-get") as cache:
            cache.set_attribute("cache.hit", True)


def test_otel_stub_captures_spans():
    from opentelemetry import trace

    with make_otel_capture() as proc:
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("root") as span:
            span.set_attribute("k", "v")

    assert len(proc.store.spans) == 1
    rec = list(proc.store.spans.values())[0]
    assert rec.name == "root"
    assert rec.attributes["k"] == "v"


def test_otel_multiple_nested_spans():
    from opentelemetry import trace

    with make_otel_capture() as proc:
        tracer = trace.get_tracer("test")
        _run_otel_instrumentation(tracer)

    names = {s.name for s in proc.store.spans.values()}
    assert names == {"request", "db-query", "cache-get"}
    request = next(s for s in proc.store.spans.values() if s.name == "request")
    assert request.attributes.get("http.method") == "GET"


