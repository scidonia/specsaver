"""SQL translation domain types."""

from __future__ import annotations

from dataclasses import dataclass, field

from specsaver import Args, Result
from specsaver.theory.sql import (
    Insert, Select, SetAdd, SetLit, SetSub, Stmt, Update,
    UnsupportedStatementError,
)


@dataclass(frozen=True)
class TranslateArgs(Args):
    sql: str
    params: tuple = ()
    outcome: str = "success"
    # Expected result fields (for success outcomes)
    stmt_kind: str = ""          # "Select" | "Insert" | "Update"
    table: str = ""
    columns: tuple[str, ...] = ()
    where_eq: tuple[tuple[str, str | int], ...] = ()
    sets: tuple[tuple[str, str], ...] = ()  # (col, expr-type) like ("reserved", "SetAdd")
    set_value: int | str | None = None      # value for single-set UPDATE
    row: tuple[tuple[str, str | int], ...] = ()
    order_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranslateResult(Result):
    stmt: Stmt | None = None


@dataclass(frozen=True)
class TranslateObserved:
    """What the service produced."""
    sql: str = ""
    params: tuple = ()
    stmt: Stmt | None = None  # None when exception raised
    exception_type: str | None = None


@dataclass(frozen=True)
class TranslateDerived:
    """Computed validation: does the result match expectations?"""
    table_ok: bool = True
    columns_ok: bool = True
    where_ok: bool = True
    sets_ok: bool = True
    row_ok: bool = True
    kind_ok: bool = True


@dataclass(frozen=True)
class TranslateState:
    observed: TranslateObserved = field(default_factory=TranslateObserved)
    derived: TranslateDerived = field(default_factory=TranslateDerived)
