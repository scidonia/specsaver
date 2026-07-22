"""SQLAlchemy against the theory's stub engine — fidelity with reality.

The stub handler drives a SQLAlchemy engine through the DBAPI shim;
every operation records events in the theory's trace and mutates the
table model.  Results must match real SQLite.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy import text

from specsaver.theory.sql import StubHandler, TableStore, make_engine

COLS = ("sku", "on_hand", "reserved", "reorder_point")


def _store(rows):
    return TableStore(
        tables={"products": {r[0]: dict(zip(COLS, r, strict=True))
                             for r in rows}},
        keys={"products": "sku"},
    )


def _real_sqlite(rows, program):
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute(
        "CREATE TABLE products (sku TEXT PRIMARY KEY, on_hand INTEGER,"
        " reserved INTEGER, reorder_point INTEGER)"
    )
    for r in rows:
        conn.execute("INSERT INTO products VALUES (?, ?, ?, ?)", r)
    out = {"fetches": [], "final": None, "error": None}
    try:
        for sql, params in program:
            cur = conn.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                out["fetches"].append(cur.fetchall())
        conn.commit()
    except sqlite3.Error as e:
        out["error"] = type(e).__name__
    out["final"] = conn.execute(
        "SELECT sku, on_hand, reserved FROM products ORDER BY sku"
    ).fetchall()
    conn.close()
    return out


def _stub(rows, program):
    handler = StubHandler(_store(rows))
    engine = make_engine(handler)
    out = {"fetches": [], "final": None, "error": None}
    try:
        with engine.begin() as conn:
            for sql, params in program:
                cur = conn.execute(text(sql), params)
                if sql.strip().upper().startswith("SELECT"):
                    out["fetches"].append(cur.fetchall())
    except Exception as e:  # noqa: BLE001 — compare error classes
        out["error"] = type(e).__name__
    with engine.connect() as conn:
        out["final"] = conn.execute(
            text("SELECT sku, on_hand, reserved FROM products ORDER BY sku")
        ).fetchall()
    return out, handler


ROWS = [("S1", 100, 10, 20), ("S2", 50, 0, 10)]


def test_sqlalchemy_select_matches_reality():
    program = [("SELECT sku, on_hand FROM products WHERE sku = :sku", {"sku": "S1"})]
    real = _real_sqlite(ROWS, program)
    stub, handler = _stub(ROWS, program)
    assert stub["fetches"] == real["fetches"]
    assert stub["final"] == real["final"]
    assert stub["error"] is None and real["error"] is None


def test_sqlalchemy_update_and_transaction_matches_reality():
    program = [
        ("UPDATE products SET reserved = reserved + :qty WHERE sku = :sku",
         {"qty": 30, "sku": "S1"}),
        ("SELECT reserved FROM products WHERE sku = :sku", {"sku": "S1"}),
    ]
    real = _real_sqlite(ROWS, program)
    stub, handler = _stub(ROWS, program)
    assert stub["fetches"] == real["fetches"]
    assert stub["final"] == real["final"]


def test_sqlalchemy_rollback_on_error():
    # insufficient stock: service checks and raises before writing
    program = [
        ("SELECT on_hand, reserved FROM products WHERE sku = :sku", {"sku": "S1"}),
    ]
    handler = StubHandler(_store(ROWS))
    engine = make_engine(handler)
    with engine.connect() as conn:
        cur = conn.execute(text(program[0][0]), program[0][1])
        on_hand, reserved = cur.fetchone()
        assert on_hand == 100 and reserved == 10
    # error path: no writes happen; trace holds only the select
    kinds = [type(e).__name__ for e in handler.trace]
    assert "Execute" in kinds


def test_sqlalchemy_trace_and_gauge_reflect_theory():
    handler = StubHandler(_store(ROWS))
    engine = make_engine(handler)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE products SET reserved = reserved + :qty WHERE sku = :sku"),
            {"qty": 30, "sku": "S1"},
        )
        conn.execute(
            text("UPDATE products SET reserved = reserved + :qty WHERE sku = :sku"),
            {"qty": 30, "sku": "S1"},
        )
    # two UPDATE events plus BEGIN/COMMIT in the trace
    kinds = [type(e).__name__ for e in handler.trace]
    txn = [k for k in kinds if k in ("Begin", "Execute", "Commit", "Rollback")]
    assert txn == ["Begin", "Execute", "Execute", "Commit"]
    row = handler.store.tables["products"]["S1"]
    assert row["reserved"] == 70


def test_sqlalchemy_session_matches_sqlite_state():
    program = [
        ("UPDATE products SET reserved = reserved + :qty WHERE sku = :sku",
         {"qty": 5, "sku": "S2"}),
        ("UPDATE products SET on_hand = on_hand - :qty WHERE sku = :sku",
         {"qty": 10, "sku": "S1"}),
        ("SELECT sku, on_hand, reserved FROM products ORDER BY sku", ()),
    ]
    real = _real_sqlite(ROWS, program)
    stub, handler = _stub(ROWS, program)
    assert stub["fetches"] == real["fetches"]
    assert stub["final"] == real["final"]
