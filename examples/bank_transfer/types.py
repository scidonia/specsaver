"""Bank transfer domain types — shared by all contract styles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from examples.bank_transfer.events import FundsReceived, TransferCompleted
from specsaver import Args, Result


@dataclass
class Account:
    id: str
    balance: int
    currency: str


@dataclass
class TransferLimits:
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
    transaction_id: str
    source_id: str
    target_id: str
    amount: int


class TransferError(Exception):
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


@dataclass(frozen=True)
class TransferObserved:
    accounts: Mapping[str, Account]
    limits: TransferLimits | None = None
    audit_log: tuple[TransferCompleted, ...] = ()
    notif_log: tuple[FundsReceived, ...] = ()


@dataclass(frozen=True)
class TransferDerived:
    total_balance: int = 0


@dataclass(frozen=True)
class TransferGhost:
    initial_total: int | None = None


@dataclass(frozen=True)
class TransferSpecState:
    observed: TransferObserved
    derived: TransferDerived
    ghost: TransferGhost = field(default_factory=TransferGhost)
