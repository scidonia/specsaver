"""Library theories — adornments that give libraries semantics.

A *theory* for a library declares, per callable, what obtains from a
call: which events it emits, which theory-state fields it reads and
writes, and how results relate to inputs.  One registry, two consumers:

  - the **stub handler** (runtime): interprets events against a pure
    model, producing the final semantic interpretation — the trace;
  - the **syntactic translator** (proof): lowers implementation code
    that calls the adorned library into theory terms.

Currently adorning: SQL, logging, OpenTelemetry.
"""

from specsaver.theory.logtheory import (  # noqa: F401 — re-export
    LOGTHEORY,
    CallRule,
    Emit,
    LogCaptureError,
    LogEmit,
    LogStore,
    LogStubHandler,
    LogTheoryError,
    make_log_capture,
)
from specsaver.theory.otel import (  # noqa: F401
    OTELTHEORY,
    OtelStore,
    OtelStubProcessor,
    OtelTheoryError,
    SpanEnded,
    SpanRecord,
    SpanStarted,
    make_otel_capture,
)
from specsaver.theory.sql import (  # noqa: F401
    SQLTHEORY,
    Begin,
    Commit,
    Execute,
    FetchAll,
    FetchOne,
    Insert,
    Rollback,
    Select,
    SetAdd,
    SetLit,
    SetSub,
    Stmt,
    StubConnection,
    StubHandler,
    TableStore,
    TheoryError,
    TheoryIntegrityError,
    UnsupportedStatementError,
    Update,
    translate_sql,
)

__all__ = [
    "SQLTHEORY",
    "LOGTHEORY",
    "OTELTHEORY",
    "Begin",
    "Commit",
    "Execute",
    "FetchAll",
    "FetchOne",
    "Insert",
    "Rollback",
    "Select",
    "SetAdd",
    "SetLit",
    "SetSub",
    "Stmt",
    "StubConnection",
    "StubHandler",
    "TableStore",
    "TheoryError",
    "TheoryIntegrityError",
    "UnsupportedStatementError",
    "Update",
    "translate_sql",
    # -- logging
    "Emit",
    "LogCaptureError",
    "LogEmit",
    "LogStore",
    "LogStubHandler",
    "LogTheoryError",
    "make_log_capture",
    # -- otel
    "OtelStore",
    "OtelStubProcessor",
    "OtelTheoryError",
    "SpanEnded",
    "SpanRecord",
    "SpanStarted",
    "make_otel_capture",
]
