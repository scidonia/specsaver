"""SQL translation — projection and contract."""

from __future__ import annotations

from specsaver.contract_model import Contract, ExcExit
from specsaver.theory.sql import Select, Insert, Update, SetAdd, SetLit, SetSub
from examples.translate.service import TranslateService
from examples.translate.types import (
    TranslateArgs, TranslateDerived, TranslateObserved, TranslateState,
)


class TranslateProjection:
    """Projects the concrete result into SpecState."""

    def snapshot(self, result: object) -> TranslateState:
        """Capture the service result as observed state."""
        from examples.translate.types import TranslateResult
        if isinstance(result, TranslateResult):
            return TranslateState(
                observed=TranslateObserved(
                    sql="", params=(),
                    stmt=result.stmt,
                    exception_type=None,
                ),
            )
        return TranslateState(
            observed=TranslateObserved(
                sql="", params=(),
                stmt=None,
                exception_type=type(result).__name__,
            ),
        )


_translation = TranslateProjection()

translate_contract = Contract(
    TranslateService.translate,
    args_type=TranslateArgs,
    feature="translate_sql.feature",
    when='the SQL <sql> with params (<params>) is translated',
    observe=_translation.snapshot,
    requires=[
        lambda state, args: args.sql != "",
    ],
    ensures=[
        # Successful SELECT: result is a Select with expected shape
        lambda old_s, args, result, new_s: (
            args.outcome != "success"
            or args.stmt_kind != "Select"
            or (
                isinstance(new_s.observed.stmt, Select)
                and new_s.observed.stmt.table == args.table
                and (not args.columns
                     or new_s.observed.stmt.columns == args.columns)
                and (not args.where_eq
                     or new_s.observed.stmt.where == args.where_eq)
            )
        ),
        # Successful INSERT
        lambda old_s, args, result, new_s: (
            args.outcome != "success"
            or args.stmt_kind != "Insert"
            or (
                isinstance(new_s.observed.stmt, Insert)
                and new_s.observed.stmt.table == args.table
                and (not args.row
                     or new_s.observed.stmt.row == args.row)
            )
        ),
        # Successful UPDATE
        lambda old_s, args, result, new_s: (
            args.outcome != "success"
            or args.stmt_kind != "Update"
            or (
                isinstance(new_s.observed.stmt, Update)
                and new_s.observed.stmt.table == args.table
                and (not args.where_eq
                     or new_s.observed.stmt.where == args.where_eq)
            )
        ),
    ],
)
