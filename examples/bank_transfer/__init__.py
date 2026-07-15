"""Bank transfer example — Gherkin → Contracts → Implementation."""

from pathlib import Path

from examples.bank_transfer.contracts import (
    FEATURE,
    Account,
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientFundsError,
    SimulatedFaultError,
    TransferArgs,
    TransferDerived,
    TransferError,
    TransferGhost,
    TransferLimits,
    TransferObserved,
    TransferReceipt,
    TransferSpecState,
    account_balance_non_negative,
    account_exists,
    has_sufficient_funds,
    is_sorted_within,
    same_currency,
    transfer_effect,
    transfer_exc_currency_mismatch,
    transfer_exc_insufficient_funds,
    transfer_exc_simulated_fault,
    transfer_post_all_balances_non_negative,
    transfer_post_error_preserves_state,
    transfer_post_source_decreased,
    transfer_post_target_increased,
    transfer_post_total_preserved,
    transfer_pre_source_exists,
    transfer_pre_target_exists,
    transfer_pre_valid_amount,
    transfer_reads_frame,
    transfer_writes_frame,
)
from examples.bank_transfer.projection import (
    TransferExecutionContext,
    TransferScenarioRunner,
    TransferScenarioWitness,
    build_witness,
    cleanup,
)
from examples.bank_transfer.service import TransferService

_FEATURE_PATH = str(Path(__file__).parent / "transfer.feature")

# Single domain runner — consumed by both CLI (--verify) and pytest tests.
transfer_runner = TransferScenarioRunner(_FEATURE_PATH, "Transfer funds")


def _verify_transfer(row, pre_only=False):
    return transfer_runner.check_pre(row) if pre_only else transfer_runner.run(row)


__verify_runner__ = {"transfer.feature": _verify_transfer}

__all__ = [
    "FEATURE",
    "Account",
    "AccountNotFoundError",
    "CurrencyMismatchError",
    "InsufficientFundsError",
    "SimulatedFaultError",
    "TransferArgs",
    "TransferReceipt",
    "TransferError",
    "TransferLimits",
    "TransferObserved",
    "TransferDerived",
    "TransferGhost",
    "TransferSpecState",
    "TransferExecutionContext",
    "TransferScenarioWitness",
    "TransferScenarioRunner",
    "TransferService",
    "transfer_runner",
    "build_witness",
    "cleanup",
    "account_balance_non_negative",
    "account_exists",
    "has_sufficient_funds",
    "is_sorted_within",
    "same_currency",
    "transfer_effect",
    "transfer_exc_currency_mismatch",
    "transfer_exc_insufficient_funds",
    "transfer_exc_simulated_fault",
    "transfer_post_all_balances_non_negative",
    "transfer_post_error_preserves_state",
    "transfer_post_source_decreased",
    "transfer_post_target_increased",
    "transfer_post_total_preserved",
    "transfer_pre_source_exists",
    "transfer_pre_target_exists",
    "transfer_pre_valid_amount",
    "transfer_reads_frame",
    "transfer_writes_frame",
]
