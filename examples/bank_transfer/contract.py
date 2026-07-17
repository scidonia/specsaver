"""Bank transfer — contract using the new Contract model.

This file describes the existing TransferService.transfer function
without modifying it.  The Contract object is standalone — no decorator
on the implementation class.

Compare with contracts.py which uses the older @precondition/@postcondition
decorator-based approach, and with service.py which uses @contract.
"""

from examples.bank_transfer.projection import TransferProjection
from examples.bank_transfer.service import TransferService
from examples.bank_transfer.types import (
    CurrencyMismatchError,
    InsufficientFundsError,
    TransferArgs,
    TransferGhost,
)
from specsaver.contract_model import Contract, ExcExit, StateField

_transfer_projection = TransferProjection()

transfer_contract = Contract(
    TransferService.transfer,
    args_type=TransferArgs,
    feature="transfer.feature",
    when='funds of <amount> are transferred from "<source>" to "<target>"',
    observe=_transfer_projection.snapshot,
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
        lambda old_s, args, result, new_s: (
            new_s.observed.accounts[args.source_id].balance
            == old_s.observed.accounts[args.source_id].balance - args.amount
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.accounts[args.target_id].balance
            == old_s.observed.accounts[args.target_id].balance + args.amount
        ),
        lambda old_s, args, result, new_s: (
            all(a.balance >= 0 for a in new_s.observed.accounts.values())
        ),
        lambda old_s, args, result, new_s: (
            len(new_s.observed.audit_log)
            == len(old_s.observed.audit_log) + 1
            and new_s.observed.audit_log[-1].transaction_id
            == result.transaction_id
        ),
        lambda old_s, args, result, new_s: (
            len(new_s.observed.notif_log)
            == len(old_s.observed.notif_log) + 1
            and new_s.observed.notif_log[-1].amount
            == args.amount
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
            ensures=[
                lambda state, args, exc, after_s: (
                    after_s.observed.accounts[args.source_id].balance
                    == state.observed.accounts[args.source_id].balance
                ),
                lambda state, args, exc, after_s: (
                    after_s.observed.accounts[args.target_id].balance
                    == state.observed.accounts[args.target_id].balance
                ),
                lambda state, args, exc, after_s: (
                    exc.source_id == args.source_id
                ),
                lambda state, args, exc, after_s: (
                    exc.amount == args.amount
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
            ensures=[
                lambda state, args, exc, after_s: (
                    after_s.observed.accounts[args.source_id].balance
                    == state.observed.accounts[args.source_id].balance
                ),
                lambda state, args, exc, after_s: (
                    after_s.observed.accounts[args.target_id].balance
                    == state.observed.accounts[args.target_id].balance
                ),
                lambda state, args, exc, after_s: (
                    exc.source_id == args.source_id
                ),
                lambda state, args, exc, after_s: (
                    exc.target_id == args.target_id
                ),
            ],
        ),
    ],
    invariants=[
        lambda state: all(a.balance >= 0 for a in state.observed.accounts.values()),
    ],
    derives={
        "total_balance": lambda state: sum(
            a.balance for a in state.observed.accounts.values()
        ),
    },
    state_schema={
        "accounts": StateField(
            type_hint="Mapping[str, Account]", provenance="observed",
        ),
        "audit_log": StateField(
            type_hint="tuple[TransferCompleted, ...]", provenance="observed",
        ),
        "notif_log": StateField(
            type_hint="tuple[FundsReceived, ...]", provenance="observed",
        ),
        "total_balance": StateField(
            type_hint="int", provenance="derived",
        ),
        "initial_total": StateField(
            type_hint="int", provenance="ghost",
        ),
    },
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
