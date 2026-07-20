"""Inventory management domain types — shared by all contract styles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from examples.inventory.events import (
    LowStockAlert,
    ReleaseFailed,
    ReservationFailed,
    ReservationReleased,
    StockLevelGauge,
    StockReceived,
    StockReserved,
)
from specsaver import Args, Result


@dataclass
class Product:
    sku: str
    on_hand: int
    reserved: int
    reorder_point: int


@dataclass(frozen=True)
class ReserveArgs(Args):
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class ReleaseArgs(Args):
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class RestockArgs(Args):
    sku: str
    quantity: int


@dataclass(frozen=True)
class ReservationReceipt(Result):
    reservation_id: str
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class ReleaseReceipt(Result):
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class RestockReceipt(Result):
    receipt_id: str
    sku: str
    quantity: int


class InventoryError(Exception):
    def __init__(self, sku: str, order_id: str, quantity: int,
                 message: str = "") -> None:
        self.sku = sku
        self.order_id = order_id
        self.quantity = quantity
        self.message = message


class InsufficientStockError(InventoryError):
    code = "INSUFFICIENT_STOCK"

    def __init__(self, sku: str, order_id: str, quantity: int,
                 available: int, message: str = "") -> None:
        super().__init__(sku, order_id, quantity, message)
        self.available = available


class ReleaseExceedsReservedError(InventoryError):
    code = "RELEASE_EXCEEDS_RESERVED"

    def __init__(self, sku: str, order_id: str, quantity: int,
                 reserved: int, message: str = "") -> None:
        super().__init__(sku, order_id, quantity, message)
        self.reserved = reserved


class ProductNotFoundError(InventoryError):
    code = "PRODUCT_NOT_FOUND"


class SimulatedFaultError(InventoryError):
    code = "FAULT_INJECTED"


@dataclass(frozen=True)
class InventoryObserved:
    products: Mapping[str, Product]
    reservation_log: tuple[StockReserved, ...] = ()
    gauge_log: tuple[StockLevelGauge, ...] = ()
    alert_log: tuple[LowStockAlert, ...] = ()
    failure_log: tuple[ReservationFailed, ...] = ()
    release_log: tuple[ReservationReleased, ...] = ()
    release_failure_log: tuple[ReleaseFailed, ...] = ()
    restock_log: tuple[StockReceived, ...] = ()


@dataclass(frozen=True)
class InventoryDerived:
    total_on_hand: int = 0
    total_reserved: int = 0
    total_available: int = 0


@dataclass(frozen=True)
class InventoryGhost:
    initial_total_on_hand: int | None = None


@dataclass(frozen=True)
class InventorySpecState:
    observed: InventoryObserved
    derived: InventoryDerived
    ghost: InventoryGhost = field(default_factory=InventoryGhost)
