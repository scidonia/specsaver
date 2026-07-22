"""Theory of OpenTelemetry — stub span processor + capture + fidelity.

The adorned library is ``opentelemetry-api`` / ``opentelemetry-sdk``.
The stub is an ``SpanProcessor`` subclass that captures every span's
full lifecycle (start, attributes, events, status, end) in a
structured ``OtelStore``, so contracts can assert on trace content
with the same ``extends_by_one`` machinery used for domain events.

Both the real OTel SDK and the stub use the same ``TracerProvider``
API — the only difference is which ``SpanProcessor`` is attached.
Differential fidelity: run the same instrumentation against both,
compare the captured spans.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import opentelemetry.trace as _otel_trace_module
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class OtelTheoryError(Exception):
    """All OTel-theory discipline errors."""


# ---------------------------------------------------------------------------
# Action / event model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpanRecord:
    """One captured span — enough to verify without the full OTel SDK."""
    name: str
    trace_id: int
    span_id: int
    parent_id: int | None
    attributes: dict[str, Any]
    events: tuple[tuple[str, dict[str, Any]], ...]
    status_code: int
    status_description: str
    start_time_ns: int
    end_time_ns: int


@dataclass(frozen=True)
class SpanStarted:
    span: SpanRecord


@dataclass(frozen=True)
class SpanEnded:
    span: SpanRecord


Event = SpanStarted | SpanEnded


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------


@dataclass
class OtelStore:
    """Accumulates all captured spans."""
    spans: dict[int, SpanRecord] = field(default_factory=dict)  # span_id -> record
    started: list[SpanRecord] = field(default_factory=list)
    ended: list[SpanRecord] = field(default_factory=list)

    def copy(self) -> OtelStore:
        return OtelStore(
            spans=dict(self.spans),
            started=list(self.started),
            ended=list(self.ended),
        )

    def __len__(self) -> int:
        return len(self.spans)


# ---------------------------------------------------------------------------
# StubSpanProcessor — captures spans for verification
# ---------------------------------------------------------------------------


class OtelStubProcessor(SpanProcessor):
    """Captures every span that passes through it into an ``OtelStore``.

    Attach this to a ``TracerProvider``, run instrumentation, then
    compare ``store.spans`` against spans captured by a real
    ``InMemorySpanExporter`` for fidelity.
    """

    def __init__(self, store: OtelStore | None = None) -> None:
        super().__init__()
        self._store = store or OtelStore()
        self._trace: list[Event] = []
        self._active = True

    def on_start(
        self,
        span: ReadableSpan,
        parent_context: Any = None,  # noqa: ARG002
    ) -> None:
        if not self._active:
            return
        record = _make_record(span)
        self._store.spans[record.span_id] = record
        self._store.started.append(record)
        self._trace.append(SpanStarted(span=record))

    def on_end(self, span: ReadableSpan) -> None:
        if not self._active:
            return
        record = _make_record(span)
        if record.span_id in self._store.spans:
            self._store.spans[record.span_id] = record
        self._store.ended.append(record)
        self._trace.append(SpanEnded(span=record))

    def shutdown(self) -> None:
        self._active = False

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    @property
    def store(self) -> OtelStore:
        return self._store

    @property
    def trace(self) -> tuple[Event, ...]:
        return tuple(self._trace)

    @property
    def active(self) -> bool:
        return self._active


def _make_record(span: ReadableSpan) -> SpanRecord:
    parent = span.parent
    return SpanRecord(
        name=span.name or "",
        trace_id=span.context.trace_id,
        span_id=span.context.span_id,
        parent_id=parent.span_id if parent is not None else None,
        attributes=dict(span.attributes or {}),
        events=tuple(
            (e.name, dict(e.attributes or {})) for e in (span.events or ())
        ),
        status_code=span.status.status_code.value,
        status_description=span.status.description or "",
        start_time_ns=(span.start_time or 0),
        end_time_ns=(span.end_time or 0),
    )


# ---------------------------------------------------------------------------
# Capture context manager
# ---------------------------------------------------------------------------


@contextmanager
def make_otel_capture() -> Iterator[OtelStubProcessor]:
    """Create a fresh SDK TracerProvider with the stub processor
    attached, set it as the global provider, run the body, yield.

    Resets the global trace state so that multiple captures in the
    same process (e.g. a parametrised test suite) work without
    OTel's one-set-guard blocking a new provider.

    Usage::

        with make_otel_capture() as proc:
            with otel_trace.get_tracer(__name__).start_as_current_span("op"):
                pass
        assert len(proc.store.spans) == 1
    """
    store = OtelStore()
    processor = OtelStubProcessor(store)
    new_provider = TracerProvider()
    new_provider.add_span_processor(processor)

    otel_trace.set_tracer_provider(new_provider)
    try:
        yield processor
    finally:
        new_provider.force_flush()
        processor.shutdown()
        new_provider.shutdown()
        # Reset the guard so the next capture can install a fresh provider
        # (do *not* call set_tracer_provider here — the warning
        #  "overriding" triggers logging recursion during tests).
        from opentelemetry.util._once import Once
        _otel_trace_module._TRACER_PROVIDER_SET_ONCE = Once()


# ---------------------------------------------------------------------------
# Adornment registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallRule:
    name: str
    emits: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    note: str = ""


OTELTHEORY: tuple[CallRule, ...] = (
    CallRule(
        name="opentelemetry.trace.Tracer.start_span",
        emits="SpanStarted",
        reads=(),
        writes=("otel_store.spans",),
        note="starting a span adds one entry to the store",
    ),
    CallRule(
        name="opentelemetry.trace.Span.end",
        emits="SpanEnded",
        reads=(),
        writes=("otel_store.spans",),
        note="ending a span finalises its record",
    ),
)
