"""Tests for specsaver.theory.sql — the SQL database theory."""


import pytest

from specsaver.theory.sql import (
    SQLTHEORY,
    Begin,
    Commit,
    Execute,
    FetchOne,
    Insert,
    Select,
    SetAdd,
    SetLit,
    SetSub,
    StubHandler,
    TableStore,
    TheoryError,
    TheoryIntegrityError,
    UnsupportedStatementError,
    Update,
    make_engine,
    translate_sql,
)

_PRODUCT_KEYS = {"products": "sku"}


def _store(rows=None):
    return TableStore(
        tables={"products": {r["sku"]: dict(r) for r in (rows or [])}},
        keys=dict(_PRODUCT_KEYS),
    )


def _product(sku, on_hand=100, reserved=10, reorder_point=20):
    return {"sku": sku, "on_hand": on_hand, "reserved": reserved,
            "reorder_point": reorder_point}


# ---------------------------------------------------------------------------
# Statement interpretation (autocommit)
# ---------------------------------------------------------------------------


def test_select_by_equality_with_projection():
    h = StubHandler(_store([_product("S1"), _product("S2", on_hand=50)]))
    n = h.execute(Select("products", ("on_hand",), where=(("sku", "S2"),)))
    assert n == 1
    assert h.fetchone() == (50,)
    assert h.fetchone() is None


def test_select_deterministic_key_order():
    h = StubHandler(_store([_product("S2"), _product("S1"), _product("S10")]))
    h.execute(Select("products", ("sku",)))
    assert h.fetchall() == (("S1",), ("S10",), ("S2",))


def test_select_unknown_table_raises():
    h = StubHandler(_store())
    with pytest.raises(TheoryError, match="no such table"):
        h.execute(Select("nope", ("x",)))


def test_insert_and_duplicate_key():
    h = StubHandler(_store([_product("S1")]))
    assert h.execute(Insert("products", tuple(_product("S2").items()))) == 1
    with pytest.raises(TheoryIntegrityError, match="duplicate key"):
        h.execute(Insert("products", tuple(_product("S2").items())))


def test_update_set_variants():
    h = StubHandler(_store([_product("S1", on_hand=100, reserved=10)]))
    n = h.execute(Update(
        "products",
        where=(("sku", "S1"),),
        sets=(("on_hand", SetSub(40)), ("reserved", SetAdd(5)),
              ("reorder_point", SetLit(99))),
    ))
    assert n == 1
    row = h.store.tables["products"]["S1"]
    assert (row["on_hand"], row["reserved"], row["reorder_point"]) == (60, 15, 99)


# ---------------------------------------------------------------------------
# Transaction discipline
# ---------------------------------------------------------------------------


def test_staged_writes_apply_on_commit():
    h = StubHandler(_store([_product("S1")]))
    h.begin()
    h.execute(Update("products", where=(("sku", "S1"),),
                     sets=(("reserved", SetAdd(30)),)))
    # Read-your-writes inside the transaction:
    h.execute(Select("products", ("reserved",), where=(("sku", "S1"),)))
    assert h.fetchone() == (40,)
    # But the committed store is untouched until commit:
    assert h.store.tables["products"]["S1"]["reserved"] == 10
    h.commit()
    assert h.store.tables["products"]["S1"]["reserved"] == 40
    assert not h.in_transaction


def test_rollback_discards_staged_writes():
    h = StubHandler(_store([_product("S1")]))
    h.begin()
    h.execute(Update("products", where=(("sku", "S1"),),
                     sets=(("reserved", SetAdd(30)),)))
    h.rollback()
    assert h.store.tables["products"]["S1"]["reserved"] == 10
    assert not h.in_transaction


def test_discipline_violations_raise():
    h = StubHandler(_store())
    with pytest.raises(TheoryError, match="COMMIT without"):
        h.commit()
    with pytest.raises(TheoryError, match="ROLLBACK without"):
        h.rollback()
    h.begin()
    with pytest.raises(TheoryError, match="inside an open transaction"):
        h.begin()


# ---------------------------------------------------------------------------
# Trace — the final interpretation
# ---------------------------------------------------------------------------


def test_trace_records_full_event_sequence():
    h = StubHandler(_store([_product("S1")]))
    h.begin()
    stmt = Update("products", where=(("sku", "S1"),),
                  sets=(("reserved", SetAdd(30)),))
    h.execute(stmt)
    h.execute(Select("products", ("reserved",), where=(("sku", "S1"),)))
    h.fetchone()
    h.commit()
    assert h.trace == (
        Begin(),
        Execute(stmt),
        Execute(Select("products", ("reserved",), where=(("sku", "S1"),))),
        FetchOne((40,)),
        Commit(),
    )


# ---------------------------------------------------------------------------
# Syntactic translation
# ---------------------------------------------------------------------------


def test_translate_select():
    stmt = translate_sql(
        "SELECT on_hand, reserved FROM products WHERE sku = ?", ("S1",))
    assert stmt == Select("products", ("on_hand", "reserved"),
                          where=(("sku", "S1"),))


def test_translate_insert():
    stmt = translate_sql(
        "INSERT INTO products (sku, on_hand) VALUES (?, ?)", ("S1", 100))
    assert stmt == Insert("products", (("sku", "S1"), ("on_hand", 100)))


def test_translate_update_arithmetic():
    stmt = translate_sql(
        "UPDATE products SET reserved = reserved + ? WHERE sku = ?", (30, "S1"))
    assert stmt == Update("products", sets=(("reserved", SetAdd(30)),),
                          where=(("sku", "S1"),))


def test_translate_rejects_outside_fragment():
    with pytest.raises(UnsupportedStatementError):
        translate_sql("DELETE FROM products WHERE sku = ?", ("S1",))
    with pytest.raises(UnsupportedStatementError):
        translate_sql("SELECT * FROM products ORDER BY sku DESC")
    with pytest.raises(UnsupportedStatementError):
        translate_sql("SELECT * FROM products WHERE on_hand > ?", (5,))
    with pytest.raises(UnsupportedStatementError):
        translate_sql(
            "SELECT * FROM products p JOIN stock s ON p.sku = s.sku")
    with pytest.raises(UnsupportedStatementError):
        translate_sql(
            "SELECT * FROM products WHERE sku IN (SELECT sku FROM stock)")


def test_translate_multiple_conjuncts_and_literals():
    stmt = translate_sql(
        "SELECT sku FROM products WHERE sku = 'S1' AND on_hand = 100"
        " AND reserved = ?",
        (3,),
    )
    assert stmt == Select(
        "products", ("sku",),
        where=(("sku", "S1"), ("on_hand", 100), ("reserved", 3)),
    )


def test_translate_update_subtract_and_mixed_sets():
    stmt = translate_sql(
        "UPDATE products SET reserved = reserved - ?, reorder_point = ?"
        " WHERE sku = ?",
        (5, 20, "S1"),
    )
    assert stmt == Update(
        "products",
        sets=(("reserved", SetSub(5)), ("reorder_point", SetLit(20))),
        where=(("sku", "S1"),),
    )


def test_translate_rejects_cross_column_set():
    with pytest.raises(UnsupportedStatementError):
        translate_sql("UPDATE products SET reserved = on_hand + ?", (1,))


# ---------------------------------------------------------------------------
# The adornment registry
# ---------------------------------------------------------------------------


def test_sqltheory_covers_connection_and_cursor_calls():
    names = {r.name for r in SQLTHEORY}
    assert "Connection.execute" in names
    assert "Connection.commit" in names
    assert "Connection.rollback" in names
    assert "Cursor.fetchone" in names
    assert all(r.emits for r in SQLTHEORY)


# ---------------------------------------------------------------------------
# End-to-end: the real InventoryService runs against the theory
# ---------------------------------------------------------------------------


def test_service_reserve_runs_against_stub():
    from examples.inventory.service import InventoryService
    from examples.inventory.types import InsufficientStockError

    handler = StubHandler(_store([_product("S1", on_hand=100, reserved=10)]))
    engine = make_engine(handler)
    receipt = InventoryService().reserve(engine, "S1", "O1", 30)

    assert receipt.quantity == 30
    assert handler.store.tables["products"]["S1"]["reserved"] == 40
    # The SELECT runs before the driver autobegins on the first write
    # (sqlite dialect do_begin is a pass).
    kinds = [type(e).__name__ for e in handler.trace]
    txn = [k for k in kinds if k in ("Begin", "Execute", "Commit", "Rollback")]
    assert txn == ["Execute", "Begin", "Execute", "Commit"]

    handler2 = StubHandler(_store([_product("S1", on_hand=100, reserved=95)]))
    engine2 = make_engine(handler2)
    with pytest.raises(InsufficientStockError):
        InventoryService().reserve(engine2, "S1", "O1", 30)
    assert handler2.store.tables["products"]["S1"]["reserved"] == 95
    kinds2 = [type(e).__name__ for e in handler2.trace]
    txn2 = [k for k in kinds2 if k in ("Begin", "Execute", "Commit", "Rollback")]
    # Read-only failure path: no transaction ever opened, so the
    # DBAPI-level rollback is a no-op and records nothing.
    assert txn2 == ["Execute"]
