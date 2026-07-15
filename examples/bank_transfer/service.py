"""Transfer service — SQLite-backed implementation.

Operates on a TransferExecutionContext.  Raises domain exceptions
(InsufficientFundsError, CurrencyMismatchError, AccountNotFoundError)
on business rejection; returns TransferReceipt on success.

The implementation has no knowledge of contracts, SpecState, or the
projection layer.
"""

from __future__ import annotations

import sqlite3

from examples.bank_transfer.contracts import (
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientFundsError,
    TransferArgs,
    TransferReceipt,
)
from examples.bank_transfer.projection import TransferExecutionContext


class TransferService:
    """Implementation of funds transfer on SQLite."""

    _counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"tx-{cls._counter:06d}"

    def execute(
        self, context: TransferExecutionContext, args: TransferArgs
    ) -> TransferReceipt:
        source_id, target_id, amount = args.source_id, args.target_id, args.amount

        with sqlite3.connect(context.db_path) as conn:
            conn.execute("BEGIN")

            srow = conn.execute(
                "SELECT balance, currency FROM accounts WHERE id = ?",
                (source_id,),
            ).fetchone()
            if srow is None:
                conn.execute("ROLLBACK")
                raise AccountNotFoundError(
                    source_id=source_id,
                    target_id=target_id,
                    amount=amount,
                    message=f"Source account {source_id!r} not found",
                )

            trow = conn.execute(
                "SELECT balance, currency FROM accounts WHERE id = ?",
                (target_id,),
            ).fetchone()
            if trow is None:
                conn.execute("ROLLBACK")
                raise AccountNotFoundError(
                    source_id=source_id,
                    target_id=target_id,
                    amount=amount,
                    message=f"Target account {target_id!r} not found",
                )

            source_balance, source_currency = srow
            target_balance, target_currency = trow

            if source_currency != target_currency:
                conn.execute("ROLLBACK")
                raise CurrencyMismatchError(
                    source_id=source_id,
                    target_id=target_id,
                    amount=amount,
                    message=(
                        f"Cannot transfer {source_currency} → {target_currency}"
                    ),
                )

            if source_balance < amount:
                conn.execute("ROLLBACK")
                raise InsufficientFundsError(
                    source_id=source_id,
                    target_id=target_id,
                    amount=amount,
                    message=f"Balance {source_balance} < amount {amount}",
                )

            conn.execute(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                (amount, source_id),
            )
            conn.execute(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                (amount, target_id),
            )
            conn.execute("COMMIT")
            context.trace.append(f"transfer:{source_id}->{target_id}:{amount}")

            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
            )
