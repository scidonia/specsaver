"""SQL translation service — thin wrapper around translate_sql."""

from __future__ import annotations

from specsaver.theory.sql import translate_sql, UnsupportedStatementError
from examples.translate.types import TranslateArgs, TranslateResult


class TranslateService:
    """The implementation under contract."""

    @staticmethod
    def translate(args: TranslateArgs) -> TranslateResult:
        """Call translate_sql, catching UnsupportedStatementError."""
        try:
            stmt = translate_sql(args.sql, args.params)
            return TranslateResult(stmt=stmt)
        except UnsupportedStatementError:
            if "unparseable" in args.outcome or "Unsupported" in args.outcome:
                return TranslateResult(stmt=None)
            raise
