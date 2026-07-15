"""Bank transfer — semantic contracts with Gherkin origin.

Every contract declares:
  - `from_gherkin` — the Gherkin step text it flows from (traceability).
  - `feature` — the feature file it belongs to.

Contracts reason over ``TransferSpecState`` — an immutable snapshot
with provenance decomposition (observed, derived, ghost).  The same
``snapshot`` projection produces both the pre-state and post-state
(symmetry requirement).

Three outcome categories:

  - **Admissibility failure** — a caller precondition fails; the
    implementation is never called.  Examples rows have
    ``outcome: rejected``.

  - **Success** — admissibility holds; the implementation returns a
    ``TransferReceipt`` without raising.  Postconditions verify the
    state transition.  Examples rows have ``outcome: success``.

  - **Exceptional outcome** — admissibility holds; the implementation
    raises a domain exception (``InsufficientFundsError``,
    ``CurrencyMismatchError``, or a fault-injected error).  The runner
    catches the exception, verifies it against the matching
    ``@exceptional`` contract, and checks that error postconditions
    (state unchanged) hold.  Examples rows have
    ``outcome: error:<CODE>``.

Feature file: transfer.feature
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from specsaver import (
    Args,
    EffectSpec,
    Event,
    Field,
    Frame,
    Result,
    effect,
    exceptional,
    forall,
    invariant,
    old,
    postcondition,
    precondition,
    predicate,
    reads,
    writes,
)

FEATURE = "transfer.feature"


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Account:
    id: str
    balance: int
    currency: str


@dataclass
class TransferLimits:
    """Transfer limits — observed state (stored in a DB table)."""

    per_transfer_max: int | None = None
    daily_remaining: int | None = None
    monthly_remaining: int | None = None


@dataclass(frozen=True)
class TransferArgs(Args):
    source_id: str
    target_id: str
    amount: int


@dataclass(frozen=True)
class TransferReceipt(Result):
    """Successful transfer outcome."""

    transaction_id: str
    source_id: str
    target_id: str
    amount: int


# -- Exception hierarchy — real Python exceptions, natural for Python -----


class TransferError(Exception):
    """Base for all transfer domain exceptions."""

    def __init__(self, source_id: str, target_id: str, amount: int,
                 message: str = "") -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.amount = amount
        self.message = message


class InsufficientFundsError(TransferError):
    code = "INSUFFICIENT_FUNDS"


class CurrencyMismatchError(TransferError):
    code = "CURRENCY_MISMATCH"


class AccountNotFoundError(TransferError):
    code = "ACCOUNT_NOT_FOUND"


class SimulatedFaultError(TransferError):
    code = "FAULT_INJECTED"


# ---------------------------------------------------------------------------
# SpecState — immutable contract-facing snapshot with provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransferObserved:
    """State read from the concrete database."""

    accounts: Mapping[str, Account]
    limits: TransferLimits | None = None


@dataclass(frozen=True)
class TransferDerived:
    """Pure values calculated from observed state."""

    total_balance: int = 0


@dataclass(frozen=True)
class TransferGhost:
    """Proof- or specification-only state — not recoverable from the DB."""

    initial_total: int | None = None


@dataclass(frozen=True)
class TransferSpecState:
    """The full contract-facing state, decomposed by provenance."""

    observed: TransferObserved
    derived: TransferDerived
    ghost: TransferGhost = field(default_factory=TransferGhost)


# ---------------------------------------------------------------------------
# Reusable predicates
# ---------------------------------------------------------------------------


@predicate
def account_exists(state: TransferSpecState, account_id: str) -> bool:
    return account_id in state.observed.accounts


@predicate
def has_sufficient_funds(
    state: TransferSpecState, account_id: str, amount: int
) -> bool:
    return state.observed.accounts[account_id].balance >= amount


@predicate
def same_currency(
    state: TransferSpecState, source_id: str, target_id: str
) -> bool:
    return (
        state.observed.accounts[source_id].currency
        == state.observed.accounts[target_id].currency
    )


@predicate
def is_sorted_within(xs: list[int], lo: int, hi: int) -> bool:
    """Structural recursion — terminates because hi - lo decreases."""
    if lo >= hi:
        return True
    return xs[lo] <= xs[lo + 1] and is_sorted_within(xs, lo + 1, hi)


# ---------------------------------------------------------------------------
# Preconditions (admissibility — true caller obligations)
# ---------------------------------------------------------------------------


@precondition(
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<source_currency>"',
    feature=FEATURE,
)
def transfer_pre_source_exists(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return args.source_id in state.observed.accounts


@precondition(
    from_gherkin='an account "<target>" with balance <target_balance>'
    ' in currency "<target_currency>"',
    feature=FEATURE,
)
def transfer_pre_target_exists(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return args.target_id in state.observed.accounts


@precondition(
    from_gherkin='funds of <amount> are transferred from "<source>" to "<target>"',
    feature=FEATURE,
)
def transfer_pre_valid_amount(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return args.amount > 0


# ---------------------------------------------------------------------------
# Exception contracts — exception type → condition (axiomander raises/ORaise)
# ---------------------------------------------------------------------------


@exceptional(
    exc_type=InsufficientFundsError,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<source_currency>"',
    feature=FEATURE,
)
def transfer_exc_insufficient_funds(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return state.observed.accounts[args.source_id].balance < args.amount


@exceptional(
    exc_type=CurrencyMismatchError,
    from_gherkin='an account "<source>" with balance <source_balance>'
    ' in currency "<source_currency>"',
    feature=FEATURE,
)
def transfer_exc_currency_mismatch(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return (
        state.observed.accounts[args.source_id].currency
        != state.observed.accounts[args.target_id].currency
    )


@exceptional(
    exc_type=SimulatedFaultError,
    from_gherkin="no account balances are changed when the transfer fails",
    feature=FEATURE,
)
def transfer_exc_simulated_fault(
    state: TransferSpecState, args: TransferArgs
) -> bool:
    return True  # fault is injected by the test harness — always applicable


# ---------------------------------------------------------------------------
# Postconditions (transitions)
# ---------------------------------------------------------------------------


@postcondition(
    from_gherkin="the total balance across all accounts is unchanged",
    feature=FEATURE,
)
def transfer_post_total_preserved(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError | Exception,
    new_s: TransferSpecState,
) -> bool:
    return old(old_s.derived.total_balance) == new_s.derived.total_balance


@postcondition(
    from_gherkin="the source balance decreased by the transfer amount",
    feature=FEATURE,
)
def transfer_post_source_decreased(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError | Exception,
    new_s: TransferSpecState,
) -> bool:
    if not isinstance(result, TransferReceipt):
        return True
    return (
        new_s.observed.accounts[args.source_id].balance
        == old(old_s.observed.accounts[args.source_id].balance) - args.amount
    )


@postcondition(
    from_gherkin="the target balance increased by the transfer amount",
    feature=FEATURE,
)
def transfer_post_target_increased(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError | Exception,
    new_s: TransferSpecState,
) -> bool:
    if not isinstance(result, TransferReceipt):
        return True
    return (
        new_s.observed.accounts[args.target_id].balance
        == old(old_s.observed.accounts[args.target_id].balance) + args.amount
    )


@postcondition(
    from_gherkin="all account balances are non-negative",
    feature=FEATURE,
)
def transfer_post_all_balances_non_negative(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError | Exception,
    new_s: TransferSpecState,
) -> bool:
    return forall(new_s.observed.accounts.values(), lambda a: a.balance >= 0)


@postcondition(
    from_gherkin="no account balances are changed when the transfer fails",
    feature=FEATURE,
)
def transfer_post_error_preserves_state(
    old_s: TransferSpecState,
    args: TransferArgs,
    result: TransferReceipt | TransferError | Exception,
    new_s: TransferSpecState,
) -> bool:
    if isinstance(result, TransferReceipt):
        return True
    return (
        old(old_s.observed.accounts[args.source_id].balance)
        == new_s.observed.accounts[args.source_id].balance
        and old(old_s.observed.accounts[args.target_id].balance)
        == new_s.observed.accounts[args.target_id].balance
    )


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


@invariant(
    from_gherkin="All account balances are non-negative at all times",
    feature=FEATURE,
)
def account_balance_non_negative(state: TransferSpecState) -> bool:
    return forall(state.observed.accounts.values(), lambda a: a.balance >= 0)


# ---------------------------------------------------------------------------
# Frame conditions
# ---------------------------------------------------------------------------


@writes(
    from_gherkin='funds of <amount> are transferred from "<source>" to "<target>"',
    feature=FEATURE,
)
def transfer_writes_frame() -> Frame:
    return Frame(
        writes={
            Field("source.balance"),
            Field("target.balance"),
            Field("audit_log"),
        }
    )


@reads(
    from_gherkin='funds of <amount> are transferred from "<source>" to "<target>"',
    feature=FEATURE,
)
def transfer_reads_frame() -> Frame:
    return Frame(
        reads={
            Field("source.balance"),
            Field("target.balance"),
            Field("source.currency"),
            Field("target.currency"),
            Field("observed.limits.daily_remaining"),
        }
    )


# ---------------------------------------------------------------------------
# Effect specification
# ---------------------------------------------------------------------------


@effect(
    from_gherkin='funds of <amount> are transferred from "<source>" to "<target>"',
    feature=FEATURE,
)
def transfer_effect() -> EffectSpec:
    return EffectSpec(
        uses={"database"},
        emits={
            Event("audit.transfer_completed"),
            Event("notification.funds_received"),
        },
    )
