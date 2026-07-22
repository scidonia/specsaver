"""Library theories — adornments that give libraries semantics.

A *theory* for a library declares, per callable, what obtains from a
call: which events it emits, which theory-state fields it reads and
writes, and how results relate to inputs.  One registry, two consumers:

  - the **stub handler** (runtime): interprets events against a pure
    model, producing the final semantic interpretation — the trace;
  - the **syntactic translator** (proof): lowers implementation code
    that calls the adorned library into theory terms.

Currently adorning: SQL (``specsaver.theory.sql``).  Logging and
OpenTelemetry theories follow the same shape.
"""

from specsaver.theory.sql import (
    SQLTHEORY,
    Begin,
    Commit,
    Event,
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
    "Begin",
    "Commit",
    "Event",
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
]
