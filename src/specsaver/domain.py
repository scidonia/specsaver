"""Domain declaration — what every SQL-backed verification domain declares.

A :class:`SqlDomain` bundles the shared infrastructure (schema,
projection, materialization) with per-operation wiring (contract,
service wrapper, witness builder).  From a single declaration the
framework derives scenario runners, the ``__verify_runner__`` CLI
dispatch dict, and the generic conformance test suite.

A new domain reduces to:

  - ``types.py``   —  domain types, args, results, errors, spec state
  - ``events.py``  —  event dataclasses (thin: just the types)
  - ``service.py`` —  the implementation (SQLAlchemy)
  - ``contract.py`` —  the specification (Contract objects)
  - ``domain.py``  —  *one* :class:`SqlDomain` instance (replaces
                       projection.py + __init__.py wiring)
  - ``*.feature``  —  Gherkin scenarios

Everything else (event log, materialization, cleanup, runner wiring,
test harness) is generic infrastructure in ``specsaver.events``,
``specsaver.domain``, and the framework conformance suite.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, create_engine, text

from specsaver.contract_model import Contract
from specsaver.events import EventLog
from specsaver.scenario_runner import ScenarioRunner

# ---------------------------------------------------------------------------
# Global domain registry — auto-populated by each SqlDomain.__post_init__
# ---------------------------------------------------------------------------

_registry: dict[str, SqlDomain] = {}

def registered_domains() -> dict[str, SqlDomain]:
    """Return every :class:`SqlDomain` that has been instantiated."""
    return dict(_registry)

# ---------------------------------------------------------------------------
# TableSpec  —  one table in the concrete database
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableSpec:
    """Declares one table: its column layout, primary key, and where the
    witness carries the initial rows."""
    name: str         # "products"
    key: str          # "sku"
    columns: tuple[str, ...]       # column ordering for INSERT / SELECT *
    witness_key: str  # "products" — attr on the witness dataclass


# ---------------------------------------------------------------------------
# SqlExecutionContext  —  concrete execution world (one type for all domains)
# ---------------------------------------------------------------------------


@dataclass
class SqlExecutionContext:
    engine: Engine
    events: EventLog = field(default_factory=EventLog)
    ghost: Any = None


# ---------------------------------------------------------------------------
# SqlProjection  —  generic snapshot from table specs + domain hooks
# ---------------------------------------------------------------------------


@dataclass
class SqlProjection:
    """Projects the concrete execution context into an immutable SpecState.

    The mechanical part (table queries → dicts) is driven by
    ``table_specs``.  Three domain hooks supply the event extraction,
    derived computation, and ghost projection — each is a single short
    function.
    """

    state_type: type
    observed_type: type
    derived_type: type
    ghost_type: type
    tables: tuple[TableSpec, ...]
    extract_observed: Callable[[SqlExecutionContext, dict[str, dict]], Any]
    compute_derived: Callable[[Any], Any]

    def snapshot(self, context: SqlExecutionContext) -> Any:
        with context.engine.connect() as conn:
            table_dicts: dict[str, dict] = {}
            for ts in self.tables:
                cols = ", ".join(ts.columns)
                rows = conn.execute(
                    text(f"SELECT {cols} FROM {ts.name}")
                ).fetchall()
                table_dicts[ts.name] = {
                    r[0]: dict(zip(ts.columns, r, strict=True))
                    for r in rows
                }

        observed = self.extract_observed(context, table_dicts)
        derived = self.compute_derived(observed)

        return self.state_type(
            observed=observed,
            derived=derived,
            ghost=context.ghost,
        )


# ---------------------------------------------------------------------------
# SqlMaterializer  —  generic temp-db creation from witness
# ---------------------------------------------------------------------------


@dataclass
class SqlMaterializer:
    """Creates a concrete execution context from a witness.

    ``populate_extra`` handles tables whose witness shape does not
    match a simple dataclass-dict (e.g.  key/value-lookup tables like
    the bank-transfer ``limits`` table).
    """

    ddl: str
    tables: tuple[TableSpec, ...]
    ghost_init: Callable[[Any], Any]
    tempfile_prefix: str = "specsaver_"
    populate_extra: Callable[[Any, sqlite3.Connection], None] | None = None

    def materialize(self, witness: Any) -> SqlExecutionContext:
        fd, path = tempfile.mkstemp(
            suffix=".db", prefix=self.tempfile_prefix,
        )
        os.close(fd)
        with sqlite3.connect(path) as conn:
            conn.executescript(self.ddl)
            for ts in self.tables:
                initial = getattr(witness, ts.witness_key, None)
                if initial is None:
                    continue
                conn.execute(f"DELETE FROM {ts.name}")
                cols = ", ".join(ts.columns)
                placeholders = ", ".join("?" * len(ts.columns))
                for obj in initial.values():
                    values = tuple(getattr(obj, c) for c in ts.columns)
                    conn.execute(
                        f"INSERT INTO {ts.name} ({cols})"
                        f" VALUES ({placeholders})",
                        values,
                    )
            if self.populate_extra is not None:
                self.populate_extra(witness, conn)

        return SqlExecutionContext(
            engine=create_engine(f"sqlite:///{path}"),
            events=EventLog(),
            ghost=self.ghost_init(witness),
        )


# ---------------------------------------------------------------------------
# SqlOperation  —  one operation (contract + wiring) within a domain
# ---------------------------------------------------------------------------


@dataclass
class SqlOperation:
    contract: Contract
    impl: Any                         # has .execute(context, args)
    witness_builder: Callable[[dict[str, str]], Any]  # row → witness
    feature_file: str                 # "reserve.feature"


# ---------------------------------------------------------------------------
# SqlDomain  —  the whole domain in one declaration
# ---------------------------------------------------------------------------


@dataclass
class SqlDomain:
    """A complete SQL-backed verification domain.

    From this single object the framework derives:
      - scenario runners (one per operation)
      - ``__verify_runner__`` dict for CLI discovery
      - the generic conformance test suite

    Usage::

        # domain.py
        inventory = SqlDomain(
            name="inventory",
            package="examples.inventory",
            materializer=SqlMaterializer(...),
            projection=SqlProjection(...),
            operations=[
                SqlOperation(reserve_contract, _FaultableReserveService(),
                             build_reserve_witness, "reserve.feature"),
                ...
            ],
        )
    """

    name: str
    package: str
    materializer: SqlMaterializer
    projection: SqlProjection
    operations: tuple[SqlOperation, ...]

    def __post_init__(self) -> None:
        # Wire the shared projection into every operation's contract.
        # The contract's ``observe`` field defaults to None — we set it
        # here so contracts can be defined without circular imports.
        snapshot = self.projection.snapshot
        for op in self.operations:
            op.contract.observe = snapshot  # type: ignore[attr-defined]
        _registry[self.package] = self

    def runners(self) -> dict[str, ScenarioRunner]:
        """Return one ScenarioRunner per operation, keyed by feature file."""
        out: dict[str, ScenarioRunner] = {}
        for op in self.operations:
            out[op.feature_file] = ScenarioRunner(
                op.contract,
                materializer=self.materializer,
                projection=self.projection,
                impl=op.impl,
                witness_builder=op.witness_builder,
                cleanup=_sql_cleanup,
            )
        return out

    def verify_runner(self) -> dict[str, Callable]:
        """``__verify_runner__`` dispatch dict for CLI discovery."""
        runners = self.runners()
        out: dict[str, Callable] = {}
        for feature, runner in runners.items():
            def _verify(row, pre_only=False, _r=runner):
                return _r.check_pre(row) if pre_only else _r.run(row)
            out[feature] = _verify
        return out

    @property
    def all_cases(self) -> list[tuple[str, SqlOperation, dict[str, str]]]:
        """Every Examples row of every feature file in this domain.

        Returns ``[(feature_file, SqlOperation, row_dict), ...]``.
        """
        # package is a Python dotted name; resolve via importlib.
        import importlib

        from specsaver.gherkin import parse_examples_tables_file

        pkg = importlib.import_module(self.package)
        pkg_dir = os.path.dirname(pkg.__file__)  # type: ignore[attr-defined]

        cases: list[tuple[str, SqlOperation, dict[str, str]]] = []
        for op in self.operations:
            fp = os.path.join(pkg_dir, op.feature_file)
            tables = parse_examples_tables_file(fp)
            for t in tables:
                cases.extend((op.feature_file, op, row) for row in t.rows)
        return cases


# ---------------------------------------------------------------------------
# Generic cleanup
# ---------------------------------------------------------------------------


def _sql_cleanup(context: SqlExecutionContext) -> None:
    path = context.engine.url.database
    context.engine.dispose()
    if path and os.path.exists(path):
        os.unlink(path)
