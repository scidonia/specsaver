"""Transfer service — SQLite-backed implementation.

The @contract decorator attaches the full specification.  The Args type
is declared explicitly — no fragile positional counting.
"""

from __future__ import annotations

import sqlite3 as _sqlite3

from examples.bank_transfer.types import (
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientFundsError,
    TransferArgs,
    TransferGhost,
    TransferReceipt,
)
from specsaver.contract_model import ExcExit, contract
from specsaver.logic import implies


@contract(
    args_type=TransferArgs,
    feature="transfer.feature",
    when='funds of <amount> are transferred from "<source>" to "<target>"',
    requires=[
        lambda state, args: args.amount > 0,
        lambda state, args: args.source_id != args.target_id,
        lambda state, args: args.source_id in state.observed.accounts,
        lambda state, args: args.target_id in state.observed.accounts,
    ],
    ensures=[
        lambda old_s, args, result, new_s: (
            old_s.derived.total_balance == new_s.derived.total_balance
        ),
        lambda old_s, args, result, new_s: implies(
            isinstance(result, TransferReceipt),
            new_s.observed.accounts[args.source_id].balance
            == old_s.observed.accounts[args.source_id].balance - args.amount,
        ),
        lambda old_s, args, result, new_s: implies(
            isinstance(result, TransferReceipt),
            new_s.observed.accounts[args.target_id].balance
            == old_s.observed.accounts[args.target_id].balance + args.amount,
        ),
        lambda old_s, args, result, new_s: implies(
            not isinstance(result, TransferReceipt),
            old_s.observed.accounts[args.source_id].balance
            == new_s.observed.accounts[args.source_id].balance
            and old_s.observed.accounts[args.target_id].balance
            == new_s.observed.accounts[args.target_id].balance,
        ),
        lambda old_s, args, result, new_s: (
            all(a.balance >= 0 for a in new_s.observed.accounts.values())
        ),
    ],
    exceptions=[
        ExcExit(
            raises=InsufficientFundsError,
            when=[
                lambda state, args: (
                    state.observed.accounts[args.source_id].currency
                    == state.observed.accounts[args.target_id].currency
                ),
                lambda state, args: (
                    state.observed.accounts[args.source_id].balance
                    < args.amount
                ),
            ],
        ),
        ExcExit(
            raises=CurrencyMismatchError,
            when=[
                lambda state, args: (
                    state.observed.accounts[args.source_id].currency
                    != state.observed.accounts[args.target_id].currency
                ),
            ],
        ),
    ],
    invariants=[
        lambda state: all(a.balance >= 0 for a in state.observed.accounts.values()),
    ],
    ghost_state=TransferGhost,
    ghost_init=lambda witness: TransferGhost(
        initial_total=sum(a.balance for a in witness["accounts"].values())
    ),
    ghost_transitions=[
        lambda old_g, args, result, new_g: (
            old_g.initial_total == new_g.initial_total
        ),
    ],
    ghost_invariants=[
        lambda state: state.ghost.initial_total is not None,
    ],
    writes={
        "state.accounts[source_id].balance",
        "state.accounts[target_id].balance",
        "state.audit_log",
        "state.notif_log",
    },
    reads={
        "state.accounts[source_id].balance",
        "state.accounts[target_id].balance",
        "state.accounts[source_id].currency",
        "state.accounts[target_id].currency",
    },
)
class TransferService:
    """Implementation — the contract is the decorator."""

    _counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._counter += 1
        return f"tx-{cls._counter:06d}"

    def transfer(
        self,
        db_path: str,
        source_id: str,
        target_id: str,
        amount: int,
    ) -> TransferReceipt:
        """Spilled-out argument list — domain adapter unpacks TransferArgs."""
        with _sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN")

            srow = conn.execute(
                "SELECT balance, currency FROM accounts WHERE id = ?",
                (source_id,),
            ).fetchone()
            if srow is None:
                conn.execute("ROLLBACK")
                raise AccountNotFoundError(source_id, "", amount,
                                           f"Source {source_id!r} not found")

            trow = conn.execute(
                "SELECT balance, currency FROM accounts WHERE id = ?",
                (target_id,),
            ).fetchone()
            if trow is None:
                conn.execute("ROLLBACK")
                raise AccountNotFoundError("", target_id, amount,
                                           f"Target {target_id!r} not found")

            source_balance, source_currency = srow
            target_balance, target_currency = trow

            if source_currency != target_currency:
                conn.execute("ROLLBACK")
                raise CurrencyMismatchError(
                    source_id, target_id, amount,
                    f"Cannot transfer {source_currency} → {target_currency}",
                )

            if source_balance < amount:
                conn.execute("ROLLBACK")
                raise InsufficientFundsError(
                    source_id, target_id, amount,
                    f"Balance {source_balance} < amount {amount}",
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

            return TransferReceipt(
                transaction_id=self._next_id(),
                source_id=source_id,
                target_id=target_id,
                amount=amount,
            )
