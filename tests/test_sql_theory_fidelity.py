"""Differential fidelity tests for the SQL theory.

Each Gherkin row is a small program of raw SQL statements (plus FETCHONE/
FETCHALL pseudo-statements).  The program runs twice:

  - **real side** — the strings execute on real SQLite (``:memory:``,
    autocommit mode so BEGIN/COMMIT/ROLLBACK are explicit);
  - **stub side** — a StubConnection translates each statement
    syntactically (sqlglot AST → Stmt) and interprets it against the
    table model.

Fetch results, final table contents, and error classes must agree —
the theory represents reality, or the scenario fails.  Select results
are compared as sets (order is not part of the relational model).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from specsaver.gherkin import (
    parse_examples_tables_file,
    parse_feature_file,
    parse_rules_file,
)
from specsaver.theory.sql import (
    StubConnection,
    StubHandler,
    TableStore,
    TheoryIntegrityError,
)

FEATURE_PATH = Path(__file__).parent / "theory" / "sql_fidelity.feature"

_CREATE = (
    "CREATE TABLE products ("
    "sku TEXT PRIMARY KEY, on_hand INTEGER NOT NULL,"
    " reserved INTEGER NOT NULL, reorder_point INTEGER NOT NULL)"
)
_DUMP = "SELECT sku, on_hand, reserved, reorder_point FROM products"


# ---------------------------------------------------------------------------
# Feature structure
# ---------------------------------------------------------------------------


def test_feature_file_exists():
    assert FEATURE_PATH.exists()


def test_rule_blocks_are_parsed():
    rules = parse_rules_file(FEATURE_PATH)
    texts = {r.text for r in rules}
    assert (
        "Every covered statement behaves identically on the stub"
        " and on real SQLite" in texts
    )


def test_feature_parses_and_outcomes_valid():
    scenarios = parse_feature_file(FEATURE_PATH)
    assert len(scenarios) == 14
    for table in parse_examples_tables_file(FEATURE_PATH):
        for row in table.rows:
            assert row["outcome"] in ("agree", "error:duplicate-key")


# ---------------------------------------------------------------------------
# The differential harness
# ---------------------------------------------------------------------------

Row = dict[str, str]


def _parse_initial(text: str) -> list[dict]:
    rows = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if chunk:
            sku, on_hand, reserved, reorder = chunk.split(":")
            rows.append({
                "sku": sku, "on_hand": int(on_hand),
                "reserved": int(reserved), "reorder_point": int(reorder),
            })
    return rows


def _parse_program(text: str) -> list[str]:
    return [s.strip() for s in text.split(";") if s.strip()]


def _run_sqlite(rows: list[dict], program: list[str]):
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(_CREATE)
    for r in rows:
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            (r["sku"], r["on_hand"], r["reserved"], r["reorder_point"]),
        )
    fetches: list = []
    error = None
    cursor = None
    try:
        for stmt in program:
            if stmt == "FETCHALL":
                assert cursor is not None, "FETCHALL before any SELECT"
                fetches.append(tuple(sorted(cursor.fetchall())))
            elif stmt == "FETCHONE":
                assert cursor is not None, "FETCHONE before any SELECT"
                fetches.append(cursor.fetchone())
            else:
                cursor = conn.execute(stmt)
    except sqlite3.IntegrityError:
        error = "duplicate-key"
    final = {
        r[0]: {"sku": r[0], "on_hand": r[1],
               "reserved": r[2], "reorder_point": r[3]}
        for r in conn.execute(_DUMP).fetchall()
    }
    conn.close()
    return fetches, final, error


def _run_stub(rows: list[dict], program: list[str]):
    store = TableStore(
        tables={"products": {r["sku"]: dict(r) for r in rows}},
        keys={"products": "sku"},
    )
    conn = StubConnection(StubHandler(store))
    fetches: list = []
    error = None
    try:
        for stmt in program:
            if stmt == "FETCHALL":
                fetches.append(tuple(sorted(conn.fetchall())))
            elif stmt == "FETCHONE":
                fetches.append(conn.fetchone())
            else:
                conn.execute(stmt)
    except TheoryIntegrityError:
        error = "duplicate-key"
    final = conn.handler.store.tables["products"]
    return fetches, final, error


# ---------------------------------------------------------------------------
# Parametrised scenarios
# ---------------------------------------------------------------------------


def _all_rows() -> list[Row]:
    rows: list[Row] = []
    for t in parse_examples_tables_file(FEATURE_PATH):
        rows.extend(t.rows)
    return rows


def _row_id(row: Row) -> str:
    program = row["program"]
    return f"{row['initial'] or 'empty'}|{program[:40]}|{row['outcome']}"


@pytest.mark.parametrize("row", _all_rows(), ids=_row_id)
def test_theory_agrees_with_reality(row: Row):
    initial = _parse_initial(row["initial"])
    program = _parse_program(row["program"])

    fetches_sql, final_sql, error_sql = _run_sqlite(initial, program)
    fetches_stub, final_stub, error_stub = _run_stub(initial, program)

    if row["outcome"] == "agree":
        assert error_sql is None and error_stub is None, (
            f"unexpected error: sqlite={error_sql} stub={error_stub}"
        )
    else:
        expected = row["outcome"].split(":", 1)[1]
        assert error_sql == expected, f"sqlite raised {error_sql}"
        assert error_stub == expected, f"stub raised {error_stub}"

    assert fetches_sql == fetches_stub, (
        f"fetch mismatch:\nsqlite: {fetches_sql}\nstub:   {fetches_stub}"
    )
    assert final_sql == final_stub, (
        f"final table mismatch:\nsqlite: {final_sql}\nstub:   {final_stub}"
    )
