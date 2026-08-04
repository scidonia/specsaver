"""Theory-aware call lowering — SQLAlchemy → SnakeletExn post-conditions.

When the lowerer encounters a library call with a registered theory
(e.g. ``conn.execute(text(sql), params)``), it replaces the call with
a SnakeletExn expression that enforces the theory's post-conditions:
dict lookups for SELECT, dict updates for UPDATE/INSERT.

The expression carries the state change as part of the program text.
At proof time, ``wp_call`` verifies that the call matches the theory's
``FunSpecS`` entry registered in the ``FunCtx`` table.
"""

from __future__ import annotations

import ast as pyast
from dataclasses import dataclass

from specsaver.theory.sql import (
    Insert,
    Select,
    SetAdd,
    SetLit,
    SetSub,
    Update,
    translate_sql,
)

from .impl_lower import (
    Expr,
    SBinOp,
    SCall,
    SInt,
    SLet,
    SLoad,
    SStore,
    SString,
    SUnit,
    SVar,
)


@dataclass(frozen=True)
class LoweredSQL:
    """One SQLAlchemy call lowered to SnakeletExn."""
    expr: Expr
    reads_state: bool
    writes_state: bool


def lower_sql_call(node: pyast.Call) -> LoweredSQL:
    """Lower ``conn.execute(text(sql), params)``.

    Extracts the SQL string and parameters, translates via the SQL
    theory, and builds the corresponding SnakeletExn expression.
    """
    sql_str, _params = _parse_execute(node)
    param_names = _collect_param_names(node)
    params = _collect_param_vals(node)
    action = translate_sql(sql_str, params)

    if isinstance(action, Select):
        return _lower_select(action, param_names)
    if isinstance(action, Update):
        return _lower_update(action, param_names)
    if isinstance(action, Insert):
        return _lower_insert(action)
    raise NotImplementedError(f"SQL action {type(action).__name__}")


def _collect_param_vals(node: pyast.Call) -> tuple:
    """Extract raw param values for translate_sql."""
    if len(node.args) < 2:
        return ()
    p = node.args[1]
    if isinstance(p, pyast.Tuple):
        return tuple(
            elt.id if isinstance(elt, pyast.Name)
            else elt.value if isinstance(elt, pyast.Constant)
            else ''
            for elt in p.elts
        )
    return ()


def _collect_param_names(node: pyast.Call) -> set[str]:
    names = set()
    if len(node.args) >= 2:
        p = node.args[1]
        if isinstance(p, pyast.Tuple):
            for e in p.elts:
                if isinstance(e, pyast.Name):
                    names.add(e.id)
    return names


def _parse_execute(node: pyast.Call) -> tuple[str, dict | None]:
    """Extract SQL string from conn.execute(text("..."), ...)."""
    sql = ""
    for arg in node.args:
        if (isinstance(arg, pyast.Call)
                and isinstance(arg.func, pyast.Name)
                and arg.func.id == "text"
                and arg.args
                and isinstance(arg.args[0], pyast.Constant)):
            sql = arg.args[0].value
    return sql, None


# ── SELECT lowering ───────────────────────────────────────────────────────


def _lower_select(action: Select, param_names: set[str] | None = None) -> LoweredSQL:
    """SELECT ... WHERE key = value → dict lookup."""
    where_cols = [c for c, _ in action.where]
    where_vals = [v for _, v in action.where]

    if len(where_cols) == 1 and isinstance(where_vals[0], str):
        key = where_vals[0]
    else:
        raise NotImplementedError("multi-column SELECT where")

    key_expr = SVar(key) if (param_names and key in param_names) else SString(key)
    return LoweredSQL(
        expr=SCall("dict_lookup_str", (key_expr, SVar("store_d"))),
        reads_state=True,
        writes_state=False,
    )


def _lower_update(action: Update, param_names=None) -> LoweredSQL:
    """UPDATE products SET col = expr WHERE key = val.

    Lowers to a let-chain that loads the store dict, looks up the row,
    computes the new field values from the old row + SET expressions,
    inserts the new row, and stores the updated dict.
    """
    key_col, key_val = action.where[0]
    key = key_val if isinstance(key_val, str) else str(key_val)
    key_expr = (SVar(key) if (param_names and key in param_names)
                else SString(key))

    # Build the expression for each set field
    # "col + value" → BinOp AddOp (dict_lookup_str "col" old_row) (value)
    # "col - value" → BinOp SubOp (dict_lookup_str "col" old_row) (value)
    # "col = value"  → value
    field_exprs: list[tuple[str, Expr]] = []
    for col, set_val in action.sets:
        old_val = SCall("dict_lookup_str",
                        (SString(col), SVar("old_row")))
        if isinstance(set_val, SetAdd):
            if isinstance(set_val.value, str):
                new_val = SBinOp("AddOp", old_val, SVar(set_val.value))
            elif isinstance(set_val.value, int):
                new_val = SBinOp("AddOp", old_val, SInt(set_val.value))
            else:
                new_val = old_val
            field_exprs.append((col, new_val))
        elif isinstance(set_val, SetSub):
            if isinstance(set_val.value, str):
                new_val = SBinOp("SubOp", old_val, SVar(set_val.value))
            elif isinstance(set_val.value, int):
                new_val = SBinOp("SubOp", old_val, SInt(set_val.value))
            else:
                new_val = old_val
            field_exprs.append((col, new_val))
        elif isinstance(set_val, SetLit):
            if isinstance(set_val.value, str):
                new_val = SString(set_val.value)
            elif isinstance(set_val.value, int):
                new_val = SInt(set_val.value)
            else:
                new_val = old_val
            field_exprs.append((col, new_val))

    # Build row_of arguments — need the full row schema.
    # For now, assume products table: on_hand, reserved, reorder_point.
    # Fields not in the SET clause keep their old value.
    _all_fields = ("on_hand", "reserved", "reorder_point")
    row_args: list[Expr] = []
    set_map = dict(field_exprs)
    for f in _all_fields:
        row_args.append(set_map.get(f) or SCall(
            "dict_lookup_str", (SString(f), SVar("old_row"))))

    new_row = SCall("row_of", tuple(row_args))

    return LoweredSQL(
        expr=SLet(
            "store_d", SLoad(SVar("store_loc")),
            SLet(
                "old_row", SCall("dict_lookup_str",
                                 (key_expr, SVar("store_d"))),
                SLet(
                    "new_row", new_row,
                    SLet(
                        "new_store",
                        SCall("dict_insert_str",
                              (key_expr, SVar("new_row"),
                               SVar("store_d"))),
                        SLet(
                            "_",
                            SStore(SVar("_heap_store"),
                                   SVar("new_store")),
                            SUnit(),
                        ),
                    ),
                ),
            ),
        ),
        reads_state=True,
        writes_state=True,
    )


def _lower_insert(action: Insert) -> LoweredSQL:
    """INSERT → dict_insert_str with a new row."""
    # noqa
    values = tuple(
        SString(v) if isinstance(v, str) else SInt(v)
        if isinstance(v, int) else SVar(str(v))
        for _, v in action.row
    )

    key_val = action.row[0][1]
    key_str = key_val if isinstance(key_val, str) else str(key_val)

    new_row = SCall("row_of", values)

    return LoweredSQL(
        expr=SLet(
            "store_d", SLoad(SVar("store_loc")),
            SLet(
                "new_row", new_row,
                SLet(
                    "new_store",
                    SCall("dict_insert_str",
                          (SString(key_str), SVar("new_row"),
                           SVar("store_d"))),
                    SLet(
                        "_",
                        SStore(SVar("_heap_store"),
                               SVar("new_store")),
                        SVar("new_row"),
                    ),
                ),
            ),
        ),
        reads_state=True,
        writes_state=True,
    )
