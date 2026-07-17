"""Bank transfer — contract using the new Contract model.

This file describes the existing TransferService.transfer function
without modifying it.  The Contract object is standalone — no decorator
on the implementation class.

Compare with contracts.py which uses the older @precondition/@postcondition
decorator-based approach, and with service.py which uses @contract.
"""

from examples.bank_transfer.events import FundsReceived, TransferCompleted
from examples.bank_transfer.projection import TransferProjection
from examples.bank_transfer.service import TransferService
from examples.bank_transfer.types import (
    CurrencyMismatchError,
    InsufficientFundsError,
    TransferArgs,
    TransferGhost,
)
from specsaver.contract_model import Contract, ExcExit

_transfer_projection = TransferProjection()

transfer_contract = Contract(
    TransferService.transfer,
    args_type=TransferArgs,
    feature="transfer.feature",
    when='funds of <amount> are transferred from "<source>" to "<target>"',
    observe=_transfer_projection.snapshot,
    requires=[
        lambda state, args: args.amount > 0,
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
    ],
    exceptions=[
        ExcExit(
            raises=InsufficientFundsError,
            when=[
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
    derives={
        "total_balance": lambda state: sum(
            a.balance for a in state.observed.accounts.values()
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
    writes={"source.balance", "target.balance", "audit_log"},
    reads={"source.balance", "target.balance", "source.currency", "target.currency"},
    uses={"database"},
    emits={
        "audit": {TransferCompleted},
        "notification": {FundsReceived},
    },
)
