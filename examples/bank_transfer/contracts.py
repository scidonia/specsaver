"""Bank transfer — semantic contracts with Gherkin origin and entry-point grouping.

Every contract declares:
  - `entry_point="transfer"` — the operation it belongs to.  This is what
    makes the full set of preconditions/postconditions for `transfer`
    discoverable via the registry (`preconditions_for`/`postconditions_for`)
    instead of relying on a test author to remember every contract name.
  - `from_gherkin` — the Gherkin step it flows from (traceability).
  - `feature` — the feature file it belongs to.

Every precondition for entry_point="transfer" shares the canonical
signature `Pre(state, args) -> bool`.  Every postcondition shares
`Post(old_state, args, result, new_state) -> bool`.  `args` is the single
structured input object `TransferArgs` (an `Args` subclass) — not a
scattered argument list — and `result` is the single structured output
object `TransferReceipt` (a `Result` subclass).  This is what lets
`specsaver.verify.run_entry_point` call every registered contract
uniformly, and lets the registry reject a mismatched Args/Result type at
registration time rather than at call time.

Feature file: transfer.feature
"""

from __future__ import annotations

from dataclasses import dataclass, field

from specsaver import (
    Args,
    EffectSpec,
    Event,
    Field,
    Frame,
    Result,
    effect,
    forall,
    ghost,
    invariant,
    old,
    postcondition,
    precondition,
    predicate,
    reads,
    writes,
)

FEATURE = "transfer.feature"
TRANSFER = "transfer"


def _build_transfer_test(row: dict[str, str]):
    """Build (state, args, impl) from a Gherkin Examples row.

    Used by `specsaver trace --verify` to auto-run tests.  Missing
    columns (e.g. ``target_balance`` for non-existent-account rows)
    silently skip that account.
    """
    source_id = row["source"]
    target_id = row["target"]
    amount = int(row["amount"])
    currency = row["currency"]

    accounts: dict[str, Account] = {}
    accounts[source_id] = Account(
        id=source_id, balance=int(row["source_balance"]), currency=currency
    )
    if "target_balance" in row:
        accounts[target_id] = Account(
            id=target_id, balance=int(row["target_balance"]), currency=currency
        )

    state = AccountState(accounts=accounts)
    args = TransferArgs(source_id=source_id, target_id=target_id, amount=amount)

    from examples.bank_transfer.service import TransferService

    impl = TransferService().transfer
    return state, args, impl


__trace_runner__ = {
    TRANSFER: _build_transfer_test,
}


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Account:
    id: str
    balance: int
    currency: str


@dataclass
class AccountState:
    accounts: dict[str, Account] = field(default_factory=dict)


@dataclass(frozen=True)
class TransferArgs(Args):
    """The single structured input to the `transfer` entry point.

    Every precondition/postcondition for entry_point="transfer" takes this
    as `args`, rather than each contract inventing its own subset of
    positional arguments.  Frozen — contracts must not mutate their input.
    """

    source_id: str
    target_id: str
    amount: int


@dataclass(frozen=True)
class TransferReceipt(Result):
    """The single structured output of the `transfer` entry point.

    Frozen — postconditions must not mutate the value they assert
    properties about.
    """

    transaction_id: str
    source_id: str
    target_id: str
    amount: int
    success: bool


# ---------------------------------------------------------------------------
# Ghost state — specification-only, not in the implementation
# ---------------------------------------------------------------------------


@ghost
class TransferLimits:
    daily_remaining: int
    monthly_remaining: int
    per_transfer_max: int


# ---------------------------------------------------------------------------
# Reusable predicates
# ---------------------------------------------------------------------------


@predicate
def account_exists(state: AccountState, account_id: str) -> bool:
    return account_id in state.accounts


@predicate
def has_sufficient_funds(state: AccountState, account_id: str, amount: int) -> bool:
    return state.accounts[account_id].balance >= amount


@predicate
def same_currency(state: AccountState, source_id: str, target_id: str) -> bool:
    return state.accounts[source_id].currency == state.accounts[target_id].currency


@predicate
def is_sorted_within(xs: list[int], lo: int, hi: int) -> bool:
    """Structural recursion — terminates because hi - lo decreases."""
    if lo >= hi:
        return True
    return xs[lo] <= xs[lo + 1] and is_sorted_within(xs, lo + 1, hi)


# ---------------------------------------------------------------------------
# Preconditions — canonical Pre(state, args) -> bool, tagged by entry point
# ---------------------------------------------------------------------------


@precondition(
    entry_point=TRANSFER,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<currency>"',
    feature=FEATURE,
)
def transfer_pre_valid_amount(state: AccountState, args: TransferArgs) -> bool:
    return args.amount > 0


@precondition(
    entry_point=TRANSFER,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<currency>"',
    feature=FEATURE,
)
def transfer_pre_accounts_exist(state: AccountState, args: TransferArgs) -> bool:
    return account_exists(state, args.source_id) and account_exists(
        state, args.target_id
    )


@precondition(
    entry_point=TRANSFER,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<currency>"',
    feature=FEATURE,
)
def transfer_pre_sufficient_funds(state: AccountState, args: TransferArgs) -> bool:
    if not account_exists(state, args.source_id):
        return False
    return has_sufficient_funds(state, args.source_id, args.amount)


@precondition(
    entry_point=TRANSFER,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<currency>"',
    feature=FEATURE,
)
def transfer_pre_same_currency(state: AccountState, args: TransferArgs) -> bool:
    if not (
        account_exists(state, args.source_id) and account_exists(state, args.target_id)
    ):
        return False
    return same_currency(state, args.source_id, args.target_id)


# ---------------------------------------------------------------------------
# Postconditions — canonical Post(old_state, args, result, new_state) -> bool
# ---------------------------------------------------------------------------


@postcondition(
    entry_point=TRANSFER,
    from_gherkin="the total balance across all accounts is unchanged",
    feature=FEATURE,
)
def transfer_post_total_preserved(
    old_s: AccountState,
    args: TransferArgs,
    result: TransferReceipt,
    new_s: AccountState,
) -> bool:
    return old(sum(a.balance for a in old_s.accounts.values())) == sum(
        a.balance for a in new_s.accounts.values()
    )


@postcondition(
    entry_point=TRANSFER,
    from_gherkin='the "<source>" balance decreased by <amount>',
    feature=FEATURE,
)
def transfer_post_source_decreased(
    old_s: AccountState,
    args: TransferArgs,
    result: TransferReceipt,
    new_s: AccountState,
) -> bool:
    return (
        new_s.accounts[args.source_id].balance
        == old(old_s.accounts[args.source_id].balance) - args.amount
    )


@postcondition(
    entry_point=TRANSFER,
    from_gherkin='the "<target>" balance increased by <amount>',
    feature=FEATURE,
)
def transfer_post_target_increased(
    old_s: AccountState,
    args: TransferArgs,
    result: TransferReceipt,
    new_s: AccountState,
) -> bool:
    return (
        new_s.accounts[args.target_id].balance
        == old(old_s.accounts[args.target_id].balance) + args.amount
    )


@postcondition(
    entry_point=TRANSFER,
    from_gherkin="all account balances are non-negative",
    feature=FEATURE,
)
def transfer_post_all_balances_non_negative(
    old_s: AccountState,
    args: TransferArgs,
    result: TransferReceipt,
    new_s: AccountState,
) -> bool:
    return forall(new_s.accounts.values(), lambda a: a.balance >= 0)


# ---------------------------------------------------------------------------
# Invariants — Inv(state) -> bool, tagged by entry point
# ---------------------------------------------------------------------------


@invariant(
    entry_point=TRANSFER,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<currency>"',
    feature=FEATURE,
)
def account_balance_non_negative(state: AccountState) -> bool:
    return forall(state.accounts.values(), lambda a: a.balance >= 0)


# ---------------------------------------------------------------------------
# Frame conditions
# ---------------------------------------------------------------------------


@writes(entry_point=TRANSFER, feature=FEATURE)
def transfer_writes_frame() -> Frame:
    return Frame(
        writes={
            Field("source.balance"),
            Field("target.balance"),
            Field("audit_log"),
        }
    )


@reads(entry_point=TRANSFER, feature=FEATURE)
def transfer_reads_frame() -> Frame:
    return Frame(
        reads={
            Field("source.balance"),
            Field("target.balance"),
            Field("source.currency"),
            Field("target.currency"),
            Field("ghost.daily_remaining"),
        }
    )


# ---------------------------------------------------------------------------
# Effect specification
# ---------------------------------------------------------------------------


@effect(entry_point=TRANSFER, feature=FEATURE)
def transfer_effect() -> EffectSpec:
    return EffectSpec(
        uses={"database"},
        emits={
            Event("audit.transfer_completed"),
            Event("notification.funds_received"),
        },
    )
