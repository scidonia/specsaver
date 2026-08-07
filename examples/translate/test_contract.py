"""SQL translation — witness builders and tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from examples.translate.contract import translate_contract
from examples.translate.types import TranslateArgs


@dataclass(frozen=True)
class TranslateWitness:
    args: TranslateArgs


def build_translate_witness(row: dict[str, str]) -> TranslateWitness:
    """Convert a Gherkin Examples row to typed arguments."""
    params_str = row.get("params", "()").strip()
    if params_str and params_str != "()":
        params = tuple(
            int(p.strip()) if p.strip().lstrip("-").isdigit()
            else p.strip().strip('"').strip("'")
            for p in params_str.strip("()").split(",") if p.strip()
        )
    else:
        params = ()

    columns_str = row.get("columns", "()").strip()
    columns: tuple[str, ...] = ()
    if columns_str and columns_str != "()":
        columns = tuple(
            c.strip().strip('"').strip("'")
            for c in columns_str.strip("()").split(",") if c.strip()
        )

    where_str = row.get("where", "()").strip()
    where_eq: tuple = ()
    if where_str and where_str != "()":
        # Parse ((key, value), ...) format
        inner = where_str.strip("()")
        if inner:
            pairs = []
            for pair in inner.split("),"):
                pair = pair.strip().strip("(")
                parts = pair.split(",", 1)
                if len(parts) == 2:
                    key = parts[0].strip().strip('"').strip("'")
                    val = parts[1].strip().strip('"').strip("'")
                    try:
                        val_int = int(val)
                        pairs.append((key, val_int))
                    except ValueError:
                        pairs.append((key, val))
            where_eq = tuple(pairs)

    return TranslateWitness(
        args=TranslateArgs(
            sql=row.get("sql", row.get("query", "")),
            params=params,
            outcome=row.get("outcome", "success"),
            stmt_kind=row.get("stmt_kind", ""),
            table=row.get("table", ""),
            columns=columns,
            where_eq=where_eq,
            sets=(),
            row=(),
        ),
    )


# ── Contract smoke tests ──────────────────────────────────────────


def test_translate_select():
    """A simple SELECT translates to a Select Stmt."""
    from specsaver.theory.sql import translate_sql
    stmt = translate_sql("SELECT on_hand FROM products WHERE sku = ?", ("S1",))
    from specsaver.theory.sql import Select
    assert isinstance(stmt, Select)
    assert stmt.table == "products"
    assert stmt.columns == ("on_hand",)
    assert stmt.where == (("sku", "S1"),)


def test_translate_insert():
    """An INSERT translates to an Insert Stmt."""
    from specsaver.theory.sql import translate_sql
    stmt = translate_sql(
        "INSERT INTO products (sku, on_hand, reserved) VALUES (?, ?, ?)",
        ("S1", 100, 10),
    )
    from specsaver.theory.sql import Insert
    assert isinstance(stmt, Insert)
    assert stmt.table == "products"
    assert stmt.row == (("sku", "S1"), ("on_hand", 100), ("reserved", 10))


def test_translate_update_add():
    """An UPDATE with addition produces SetAdd."""
    from specsaver.theory.sql import translate_sql, Update, SetAdd
    stmt = translate_sql(
        "UPDATE products SET reserved = reserved + ? WHERE sku = ?", (30, "S1"),
    )
    assert isinstance(stmt, Update)
    assert stmt.table == "products"
    assert stmt.sets[0] == ("reserved", SetAdd(30))


def test_translate_update_sub():
    """An UPDATE with subtraction produces SetSub."""
    from specsaver.theory.sql import translate_sql, Update, SetSub
    stmt = translate_sql(
        "UPDATE products SET reserved = reserved - ? WHERE sku = ?", (5, "S1"),
    )
    assert isinstance(stmt, Update)
    assert stmt.sets[0] == ("reserved", SetSub(5))


def test_translate_update_literal():
    """An UPDATE with literal produces SetLit."""
    from specsaver.theory.sql import translate_sql, Update, SetLit
    stmt = translate_sql(
        "UPDATE products SET status = ? WHERE sku = ?", ("sold", "S1"),
    )
    assert isinstance(stmt, Update)
    assert stmt.sets[0] == ("status", SetLit("sold"))


def test_translate_unsupported_raises():
    """Unsupported SQL raises UnsupportedStatementError."""
    from specsaver.theory.sql import translate_sql, UnsupportedStatementError
    with pytest.raises(UnsupportedStatementError):
        translate_sql("DELETE FROM products", ())


def test_translate_unparseable_raises():
    """Garbage SQL raises UnsupportedStatementError."""
    from specsaver.theory.sql import translate_sql, UnsupportedStatementError
    with pytest.raises(UnsupportedStatementError):
        translate_sql("garbage", ())


def test_translate_empty_raises():
    """Empty SQL raises UnsupportedStatementError."""
    from specsaver.theory.sql import translate_sql, UnsupportedStatementError
    with pytest.raises(UnsupportedStatementError):
        translate_sql("", ())
