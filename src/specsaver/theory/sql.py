"""A theory of SQL databases — the first library adornment.

The theory has three parts:

1. **Statement model** — the initial algebra: structured statements
   (``Select``/``Insert``/``Update`` with equality predicates only).
   Raw SQL strings in the covered fragment translate syntactically via
   :func:`translate_sql`; anything outside raises
   :class:`UnsupportedStatementError`, loudly, by design.

2. **Event signature** — the observable behaviour of a database
   connection: ``Begin``, ``Execute``, ``FetchOne``, ``FetchAll``,
   ``Commit``, ``Rollback``.  A program's *final semantic
   interpretation* is its ``(result, trace)`` pair; contracts quantify
   over the trace, never over the mechanics.

3. **Stub handler** — the pure operational semantics: events are
   interpreted against a :class:`TableStore`.  Writes stage inside a
   transaction and apply at ``Commit`` (read-your-writes within the
   transaction); ``Rollback`` discards them.  Usage outside the
   discipline raises :class:`TheoryError`.

The adornment registry (:data:`SQLTHEORY`) states per callable what
obtains from a call — events emitted, theory-state read/written —
the data a syntactic translator consumes when lowering implementation
code into theory terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import exp


class TheoryError(Exception):
    """Discipline violation: the theory was used outside its rules."""


class UnsupportedStatementError(TheoryError):
    """The statement is outside the theory's covered fragment."""


class TheoryIntegrityError(TheoryError):
    """A constraint of the table model was violated (e.g. duplicate key)."""


# ---------------------------------------------------------------------------
# Statement model (initial algebra)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Select:
    table: str
    columns: tuple[str, ...]            # empty tuple = all columns
    where: tuple[tuple[str, Any], ...] = ()   # equality conjuncts
    order_by: tuple[str, ...] = ()      # ORDER BY columns (explicit order)


@dataclass(frozen=True)
class Insert:
    table: str
    row: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class SetLit:
    value: Any


@dataclass(frozen=True)
class SetAdd:
    value: Any


@dataclass(frozen=True)
class SetSub:
    value: Any


@dataclass(frozen=True)
class Update:
    table: str
    where: tuple[tuple[str, Any], ...]
    sets: tuple[tuple[str, Any], ...]   # (col, SetLit|SetAdd|SetSub)


Stmt = Select | Insert | Update


# ---------------------------------------------------------------------------
# Event signature (final interpretation: the trace)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Begin:
    pass


@dataclass(frozen=True)
class Execute:
    stmt: Stmt


@dataclass(frozen=True)
class FetchOne:
    row: tuple | None


@dataclass(frozen=True)
class FetchAll:
    rows: tuple[tuple, ...]


@dataclass(frozen=True)
class Commit:
    pass


@dataclass(frozen=True)
class Rollback:
    pass


Event = Begin | Execute | FetchOne | FetchAll | Commit | Rollback


# ---------------------------------------------------------------------------
# Table model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableStore:
    """A pure relational store: table name → {primary key → row}.

    ``keys`` names the primary-key column per table.  Rows are plain
    dicts.  Immutable from the handler's perspective — transactions
    stage a deep copy and swap on commit.
    """

    tables: dict[str, dict[Any, dict[str, Any]]]
    keys: dict[str, str]

    def copy_tables(self) -> dict[str, dict[Any, dict[str, Any]]]:
        return {t: {k: dict(r) for k, r in rows.items()}
                for t, rows in self.tables.items()}

    def with_tables(
        self, tables: dict[str, dict[Any, dict[str, Any]]]
    ) -> TableStore:
        return TableStore(tables=tables, keys=self.keys)


# ---------------------------------------------------------------------------
# Stub handler — the pure operational semantics
# ---------------------------------------------------------------------------


class StubHandler:
    """Interprets events against a TableStore, recording the trace.

    Discipline: ``begin`` opens a transaction (writes stage);
    ``commit`` applies the stage; ``rollback`` discards it.  Executes
    outside a transaction apply immediately (autocommit).
    ``commit``/``rollback`` without an open transaction raise
    :class:`TheoryError`.
    """

    def __init__(self, store: TableStore) -> None:
        self._store = store
        self._staged: dict[str, dict[Any, dict[str, Any]]] | None = None
        self._trace: list[Event] = []
        self._cursor: list[tuple] = []
        self._cursor_rowcount: int = 0
        self.autobegin_on_dml: bool = False

    @property
    def store(self) -> TableStore:
        return self._store

    @property
    def trace(self) -> tuple[Event, ...]:
        return tuple(self._trace)

    @property
    def in_transaction(self) -> bool:
        return self._staged is not None

    def _tables(self) -> dict[str, dict[Any, dict[str, Any]]]:
        return self._staged if self._staged is not None else self._store.tables

    # -- connection events -------------------------------------------------

    def begin(self) -> None:
        if self._staged is not None:
            raise TheoryError("BEGIN inside an open transaction")
        self._staged = self._store.copy_tables()
        self._trace.append(Begin())

    def commit(self) -> None:
        if self._staged is None:
            raise TheoryError("COMMIT without an open transaction")
        self._store = self._store.with_tables(self._staged)
        self._staged = None
        self._trace.append(Commit())

    def rollback(self) -> None:
        if self._staged is None:
            raise TheoryError("ROLLBACK without an open transaction")
        self._staged = None
        self._trace.append(Rollback())

    # -- statement execution ------------------------------------------------

    def execute(self, stmt: Stmt) -> int:
        """Interpret a statement.  Returns the affected row count
        (for Select, the number of rows loaded into the cursor).

        Models the sqlite3 driver's autobegin: a DML statement (INSERT
        or UPDATE) executed with no open transaction opens one first.
        """
        if (
            self.autobegin_on_dml
            and self._staged is None
            and isinstance(stmt, (Insert, Update))
        ):
            self.begin()
        if isinstance(stmt, Select):
            n = self._exec_select(stmt)
        elif isinstance(stmt, Insert):
            n = self._exec_insert(stmt)
        elif isinstance(stmt, Update):
            n = self._exec_update(stmt)
        else:
            raise UnsupportedStatementError(
                f"statement outside the theory: {stmt!r}"
            )
        self._trace.append(Execute(stmt))
        self._cursor_rowcount = n
        return n

    def _exec_select(self, stmt: Select) -> int:
        rows = self._tables().get(stmt.table)
        if rows is None:
            raise TheoryError(f"no such table: {stmt.table!r}")
        keys = sorted(rows, key=str)
        if stmt.order_by:
            keys = sorted(
                keys,
                key=lambda k: tuple(rows[k][c] for c in stmt.order_by),
            )
        out: list[tuple] = []
        for pk in keys:
            row = rows[pk]
            if all(row.get(c) == v for c, v in stmt.where):
                if stmt.columns:
                    out.append(tuple(row[c] for c in stmt.columns))
                else:
                    out.append(tuple(row[c] for c in sorted(row)))
        self._cursor = out
        return len(out)

    def _exec_insert(self, stmt: Insert) -> int:
        tables = self._tables()
        if stmt.table not in self._store.keys:
            raise TheoryError(f"no such table: {stmt.table!r}")
        row = dict(stmt.row)
        key_col = self._store.keys[stmt.table]
        pk = row.get(key_col)
        if pk is None:
            raise TheoryIntegrityError(
                f"insert into {stmt.table!r} lacks key column {key_col!r}"
            )
        table = tables.setdefault(stmt.table, {})
        if pk in table:
            raise TheoryIntegrityError(
                f"duplicate key {pk!r} in table {stmt.table!r}"
            )
        table[pk] = row
        return 1

    def _exec_update(self, stmt: Update) -> int:
        tables = self._tables()
        rows = tables.get(stmt.table)
        if rows is None:
            raise TheoryError(f"no such table: {stmt.table!r}")
        n = 0
        for pk in list(rows):
            row = rows[pk]
            if all(row.get(c) == v for c, v in stmt.where):
                for col, setexpr in stmt.sets:
                    if isinstance(setexpr, SetLit):
                        row[col] = setexpr.value
                    elif isinstance(setexpr, SetAdd):
                        row[col] = row[col] + setexpr.value
                    elif isinstance(setexpr, SetSub):
                        row[col] = row[col] - setexpr.value
                    else:
                        raise UnsupportedStatementError(
                            f"unsupported SET expression: {setexpr!r}"
                        )
                n += 1
        return n

    # -- cursor events -------------------------------------------------------

    def fetchone(self) -> tuple | None:
        row = self._cursor.pop(0) if self._cursor else None
        self._trace.append(FetchOne(row))
        return row

    def fetchall(self) -> tuple[tuple, ...]:
        rows = tuple(self._cursor)
        self._cursor = []
        self._trace.append(FetchAll(rows))
        return rows


# ---------------------------------------------------------------------------
# Syntactic translation — raw SQL strings → Stmt via a real AST (sqlglot)
# ---------------------------------------------------------------------------


def _literal(node: exp.Expression, params: list) -> Any:
    """Convert a Placeholder/Literal to a concrete value, consuming params
    left-to-right (SQL parameter order)."""
    if isinstance(node, exp.Placeholder):
        if not params:
            raise UnsupportedStatementError("not enough parameters")
        return params.pop(0)
    if isinstance(node, exp.Literal):
        return node.this if node.is_string else int(node.this)
    if isinstance(node, exp.Neg) and isinstance(node.this, exp.Literal):
        return -int(node.this.this)
    raise UnsupportedStatementError(f"value outside the theory: {node.sql()!r}")


def _column(node: exp.Expression) -> str:
    if not isinstance(node, exp.Column):
        raise UnsupportedStatementError(
            f"expected a column, got {node.sql()!r}"
        )
    return node.name


def _eq_conjuncts(
    node: exp.Expression | None, params: list
) -> tuple[tuple[str, Any], ...]:
    """Flatten a WHERE clause into equality conjuncts — anything else
    (ordering, inequalities, subqueries) is outside the theory."""
    if node is None:
        return ()
    conjuncts = node.flatten() if isinstance(node, exp.And) else [node]
    out = []
    for c in conjuncts:
        if not isinstance(c, exp.EQ):
            raise UnsupportedStatementError(
                f"WHERE conjunct outside the theory: {c.sql()!r}"
            )
        out.append((_column(c.left), _literal(c.right, params)))
    return tuple(out)


def _reject_select_modifiers(tree: exp.Select) -> None:
    for key in ("group", "limit", "joins", "having", "distinct"):
        if tree.args.get(key):
            raise UnsupportedStatementError(
                f"SELECT with {key.upper()} outside the theory"
            )
    order = tree.args.get("order")
    if order and not all(
        isinstance(o.this, exp.Column) and not o.args.get("desc")
        for o in order.expressions
    ):
        raise UnsupportedStatementError(
            "SELECT ORDER BY form outside the theory"
        )


def _order_columns(tree: exp.Select) -> tuple[str, ...]:
    order = tree.args.get("order")
    if order is None:
        return ()
    return tuple(o.this.name for o in order.expressions)


def translate_sql(sql: str, params: tuple = ()) -> Stmt:
    """Translate a raw SQL string in the covered fragment to a Stmt.

    Parses with sqlglot (sqlite dialect) — a real AST, no regex munging —
    then walks the tree.  Covered: ``SELECT cols FROM t [WHERE c = ? AND
    ...]``, ``INSERT INTO t (cols) VALUES (?, ...)``, ``UPDATE t SET
    c = ? | c = c + ? | c = c - ? [, ...] [WHERE ...]``.  Anything else
    raises :class:`UnsupportedStatementError`.
    """
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception as exc:
        raise UnsupportedStatementError(
            f"unparseable statement: {sql!r}"
        ) from exc
    remaining = list(params)

    if isinstance(tree, exp.Select):
        _reject_select_modifiers(tree)
        from_ = tree.args.get("from_")
        if from_ is None or not isinstance(from_.this, exp.Table):
            raise UnsupportedStatementError(
                f"SELECT source outside the theory: {sql!r}"
            )
        cols = tree.expressions
        if len(cols) == 1 and isinstance(cols[0], exp.Star):
            columns: tuple[str, ...] = ()
        elif all(isinstance(c, exp.Column) for c in cols):
            columns = tuple(c.name for c in cols)
        else:
            raise UnsupportedStatementError(
                f"SELECT columns outside the theory: {sql!r}"
            )
        where = tree.args.get("where")
        return Select(
            table=from_.this.name,
            columns=columns,
            where=_eq_conjuncts(where.this if where else None, remaining),
            order_by=_order_columns(tree),
        )

    if isinstance(tree, exp.Insert):
        schema = tree.this
        if not isinstance(schema, exp.Schema):
            raise UnsupportedStatementError(
                f"INSERT target outside the theory: {sql!r}"
            )
        values = tree.args.get("expression")
        if not isinstance(values, exp.Values) or len(values.expressions) != 1:
            raise UnsupportedStatementError(
                f"INSERT values outside the theory: {sql!r}"
            )
        row_vals = values.expressions[0].expressions
        cols = [c.name for c in schema.expressions]
        if len(cols) != len(row_vals):
            raise UnsupportedStatementError(
                f"column/value count mismatch in {sql!r}"
            )
        return Insert(
            table=schema.this.name,
            row=tuple(
                (c, _literal(v, remaining))
                for c, v in zip(cols, row_vals, strict=True)
            ),
        )

    if isinstance(tree, exp.Update):
        table = tree.this
        if not isinstance(table, exp.Table):
            raise UnsupportedStatementError(
                f"UPDATE target outside the theory: {sql!r}"
            )
        sets = []
        for assign in tree.expressions:
            if not isinstance(assign, exp.EQ) or not isinstance(
                assign.left, exp.Column
            ):
                raise UnsupportedStatementError(
                    f"SET clause outside the theory: {assign.sql()!r}"
                )
            col = assign.left.name
            rhs = assign.right
            if isinstance(rhs, (exp.Add, exp.Sub)):
                if not isinstance(rhs.left, exp.Column) or rhs.left.name != col:
                    raise UnsupportedStatementError(
                        f"SET clause outside the theory: {assign.sql()!r}"
                    )
                value = _literal(rhs.right, remaining)
                sets.append(
                    (col, SetAdd(value) if isinstance(rhs, exp.Add)
                     else SetSub(value))
                )
            else:
                sets.append((col, SetLit(_literal(rhs, remaining))))
        where = tree.args.get("where")
        return Update(
            table=table.name,
            sets=tuple(sets),
            where=_eq_conjuncts(where.this if where else None, remaining),
        )

    raise UnsupportedStatementError(f"statement outside the theory: {sql!r}")


# ---------------------------------------------------------------------------
# StubConnection — a DBAPI-flavoured facade over the handler
# ---------------------------------------------------------------------------


class StubConnection:
    """Speaks a sqlite3-shaped dialect while interpreting every call
    through the theory.  Implementation code written against a plain
    connection runs against the stub unmodified; the trace falls out.
    """

    def __init__(self, handler: StubHandler) -> None:
        self._handler = handler

    def __enter__(self) -> StubConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @property
    def handler(self) -> StubHandler:
        return self._handler

    def execute(self, sql: str, params: tuple = ()) -> StubConnection:
        sql_stripped = sql.strip().rstrip(";")
        if sql_stripped.upper() == "BEGIN":
            self._handler.begin()
            return self
        if sql_stripped.upper() == "COMMIT":
            self._handler.commit()
            return self
        if sql_stripped.upper() == "ROLLBACK":
            self._handler.rollback()
            return self
        self._handler.execute(translate_sql(sql, params))
        return self

    def fetchone(self) -> tuple | None:
        return self._handler.fetchone()

    def fetchall(self) -> tuple[tuple, ...]:
        return self._handler.fetchall()

    def commit(self) -> None:
        self._handler.commit()

    def rollback(self) -> None:
        self._handler.rollback()


# ---------------------------------------------------------------------------
# DBAPI 2.0 (PEP 249) shim — SQLAlchemy speaks to the theory through it.
# ---------------------------------------------------------------------------


class Error(Exception):
    """DBAPI error hierarchy (mirrors sqlite3's class names)."""


class DatabaseError(Error):
    pass


class IntegrityError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


class InterfaceError(Error):
    pass


class DataError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


apilevel = "2.0"
threadsafety = 3
paramstyle = "qmark"
sqlite_version_info = (3, 40, 0)


def _dbapi_error(exc: TheoryError) -> DatabaseError:
    if isinstance(exc, TheoryIntegrityError):
        return IntegrityError(str(exc))
    if isinstance(exc, UnsupportedStatementError):
        return NotSupportedError(str(exc))
    return OperationalError(str(exc))


class StubCursor:
    """A PEP 249 cursor whose statements are translated and interpreted
    by the theory's StubHandler."""

    def __init__(self, handler: StubHandler) -> None:
        self._handler = handler
        self._last_stmt: Stmt | None = None
        self._closed = False

    def execute(self, sql: str, parameters: tuple = ()) -> StubCursor:
        sql_stripped = sql.strip().rstrip(";")
        if sql_stripped.upper().startswith("PRAGMA"):
            # Pragmas affect isolation/storage mechanics, which are
            # outside the theory's covered fragment — a no-op.
            return self
        try:
            if sql_stripped.upper() == "BEGIN":
                self._handler.begin()
                self._last_stmt = None
                return self
            if sql_stripped.upper() == "COMMIT":
                self._handler.commit()
                self._last_stmt = None
                return self
            if sql_stripped.upper() == "ROLLBACK":
                self._handler.rollback()
                self._last_stmt = None
                return self
            stmt = translate_sql(sql, parameters)
            self._handler.execute(stmt)
            self._last_stmt = stmt
            return self
        except TheoryError as exc:
            raise _dbapi_error(exc) from exc

    @property
    def rowcount(self) -> int:
        return self._handler._cursor_rowcount

    @property
    def description(self) -> list[tuple] | None:
        stmt = self._last_stmt
        if stmt is None or not isinstance(stmt, Select):
            return None
        if stmt.columns:
            return [(c, None, None, None, None, None, None)
                    for c in stmt.columns]
        rows = self._handler._cursor
        if not rows:
            return None
        # SELECT * — describe from the first row's stored columns is not
        # available at this level; report nothing extra (SQLAlchemy falls
        # back to positional access).
        return None

    def fetchone(self) -> tuple | None:
        return self._handler.fetchone()

    def fetchall(self) -> tuple[tuple, ...]:
        return self._handler.fetchall()

    def fetchmany(self, size: int) -> list[tuple]:
        out = []
        for _ in range(size):
            row = self._handler.fetchone()
            if row is None:
                break
            out.append(row)
        return out

    def close(self) -> None:
        self._closed = True


class DbapiConnection(StubConnection):
    """A PEP 249 connection over the theory — the object SQLAlchemy
    drives through its sqlite dialect."""

    def __init__(self, handler: StubHandler) -> None:
        super().__init__(handler)
        self.isolation_level: str | None = ""
        # SQLAlchemy's sqlite dialect relies on the driver's deferred
        # autobegin for commit/rollback to pair — enable it for this path.
        handler.autobegin_on_dml = True

    def cursor(self) -> StubCursor:
        return StubCursor(self._handler)

    def execute(self, sql: str, parameters: tuple = ()) -> StubCursor:  # type: ignore[override]
        cursor = self.cursor()
        return cursor.execute(sql, parameters)

    def create_function(self, name: str, num_params: int, func, **kwargs) -> None:
        """DBAPI hook for SQL function registration — a no-op in the
        theory (functions outside the covered fragment are unsupported)."""

    def commit(self) -> None:
        """Python sqlite3 semantics: commit() is a no-op when no
        transaction is open."""
        if self._handler.in_transaction:
            self._handler.commit()

    def rollback(self) -> None:
        """Python sqlite3 semantics: rollback() is a no-op when no
        transaction is open."""
        if self._handler.in_transaction:
            self._handler.rollback()

    def close(self) -> None:
        pass


def connect(handler: StubHandler) -> DbapiConnection:
    """DBAPI ``connect()`` entry point for the stub."""
    return DbapiConnection(handler)


def make_engine(handler: StubHandler):
    """Build a SQLAlchemy engine whose every connection is the theory's
    stub handler (single static connection, so transactions behave)."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    return create_engine(
        "sqlite://",
        creator=lambda: connect(handler),
        poolclass=StaticPool,
    )


# ---------------------------------------------------------------------------
# The adornment registry — what obtains from each call
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallRule:
    """What obtains from a call into the adorned library.

    ``reads``/``writes`` are fields of the theory state (``store``,
    ``staged``, ``cursor``, ``tx``, ``trace``).  ``emits`` names the
    event constructor(s) the call appends to the trace.
    """

    name: str
    emits: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    note: str = ""


SQLTHEORY: tuple[CallRule, ...] = (
    CallRule(
        "Connection.begin", "Begin", (), ("tx", "trace"),
        "opens a transaction; subsequent writes stage",
    ),
    CallRule(
        "Connection.execute", "Execute",
        ("staged", "store"), ("staged", "cursor", "trace"),
        "statement interpreted against the staged store; "
        "Select loads the cursor (read-your-writes)",
    ),
    CallRule(
        "Cursor.fetchone", "FetchOne", ("cursor",), ("cursor", "trace"),
        "next cursor row, or None when drained",
    ),
    CallRule(
        "Cursor.fetchall", "FetchAll", ("cursor",), ("cursor", "trace"),
        "drains the cursor",
    ),
    CallRule(
        "Connection.commit", "Commit", ("staged",), ("store", "tx", "trace"),
        "staged writes apply atomically",
    ),
    CallRule(
        "Connection.rollback", "Rollback", (), ("staged", "tx", "trace"),
        "staged writes are discarded",
    ),
)
