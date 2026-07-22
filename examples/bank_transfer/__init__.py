"""Bank transfer example — Gherkin → Contracts → Implementation."""

from pathlib import Path

from examples.bank_transfer.domain import transfer_domain as _domain
from examples.bank_transfer.projection import build_witness
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

_runners = _domain.runners()
transfer_runner = _runners["transfer.feature"]

__verify_runner__ = _domain.verify_runner()

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
    "TransferService",
    "transfer_runner",
    "build_witness",
]
