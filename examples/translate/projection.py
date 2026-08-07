"""SQL translation — projection and witness builder."""

from __future__ import annotations

from dataclasses import dataclass

from examples.translate.types import TranslateArgs


class TranslateProjection:
    """Projects the concrete result into SpecState for contract checking."""

    def snapshot(self, result_or_exc):
        from examples.translate.types import (
            TranslateObserved, TranslateDerived, TranslateState,
        )
        if isinstance(result_or_exc, Exception):
            return TranslateState(
                observed=TranslateObserved(
                    exception_type=type(result_or_exc).__name__,
                ),
                derived=TranslateDerived(),
            )
        return TranslateState(
            observed=TranslateObserved(
                stmt=result_or_exc if result_or_exc is not None else None,
            ),
            derived=TranslateDerived(),
        )


@dataclass(frozen=True)
class TranslateScenarioWitness:
    args: TranslateArgs


def build_witness(row: dict[str, str]) -> TranslateScenarioWitness:
    """Map a translate_sql.feature Examples row to typed args."""

    def _parse_int_or_str(s: str):
        s = s.strip().strip('"').strip("'")
        if s.lstrip("-").isdigit():
            return int(s)
        return s

    sql = row.get("sql", row.get("query", ""))
    params_str = row.get("params", "").strip("()")
    params = ()
    if params_str:
        params = tuple(_parse_int_or_str(p) for p in params_str.split(",") if p.strip())

    outcome = row.get("outcome", "success")
    stmt_kind = ""
    columns: tuple[str, ...] = ()
    where_eq: tuple = ()
    sets: tuple = ()

    # Parse expected columns from "cols" or "columns" field
    cols_str = row.get("columns", row.get("cols", "()")).strip("()")
    if cols_str:
        columns = tuple(
            c.strip().strip('"').strip("'")
            for c in cols_str.split(",") if c.strip()
        )

    # Parse table from feature row
    table = row.get("table", "")

    # Parse where clause
    where_str = row.get("where", "()").strip("()")
    if where_str:
        pairs = []
        for pair_str in where_str.split("),"):
            pair_str = pair_str.strip().strip("(")
            parts = pair_str.split(",", 1)
            if len(parts) == 2:
                key = parts[0].strip().strip('"').strip("'")
                val = _parse_int_or_str(parts[1])
                pairs.append((key, val))
        where_eq = tuple(pairs)

    # Determine statement kind from the query or stmt_kind field
    if row.get("stmt_kind"):
        stmt_kind = row["stmt_kind"]
    elif "SELECT" in sql.upper():
        stmt_kind = "Select"
    elif "INSERT" in sql.upper():
        stmt_kind = "Insert"
    elif "UPDATE" in sql.upper():
        stmt_kind = "Update"

    return TranslateScenarioWitness(
        args=TranslateArgs(
            sql=sql,
            params=params,
            outcome=outcome,
            stmt_kind=stmt_kind,
            table=table,
            columns=columns,
            where_eq=where_eq,
            sets=sets,
        ),
    )
