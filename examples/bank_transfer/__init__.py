"""Bank transfer example — Gherkin → Contracts → Implementation."""

from pathlib import Path

from examples.bank_transfer.projection import (
    TransferExecutionContext,
    TransferScenarioRunner,
    TransferScenarioWitness,
    build_witness,
    cleanup,
)
from examples.bank_transfer.service import TransferService
from examples.bank_transfer.types import (
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
)

FEATURE = "transfer.feature"

_FEATURE_PATH = str(Path(__file__).parent / "transfer.feature")

# Single domain runner — consumed by both CLI (--verify) and pytest tests.
transfer_runner = TransferScenarioRunner()


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
]
