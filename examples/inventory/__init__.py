"""Inventory example — Gherkin → Contracts → Implementation."""

from examples.inventory.contract import (
    release_contract,
    reserve_contract,
    restock_contract,
)
from examples.inventory.domain import inventory as _domain
from examples.inventory.projection import (
    build_release_witness,
    build_reserve_witness,
    build_restock_witness,
)
from examples.inventory.service import InventoryService
from examples.inventory.types import (
    InsufficientStockError,
    InventoryDerived,
    InventoryError,
    InventoryGhost,
    InventoryObserved,
    InventorySpecState,
    Product,
    ProductNotFoundError,
    ReleaseArgs,
    ReleaseExceedsReservedError,
    ReleaseReceipt,
    ReservationReceipt,
    ReserveArgs,
    RestockArgs,
    RestockReceipt,
    SimulatedFaultError,
)

FEATURE = "reserve.feature"

_runners = _domain.runners()
reserve_runner = _runners["reserve.feature"]
release_runner = _runners["release.feature"]
restock_runner = _runners["restock.feature"]

__verify_runner__ = _domain.verify_runner()

__all__ = [
    "FEATURE",
    "InsufficientStockError",
    "InventoryDerived",
    "InventoryError",
    "InventoryGhost",
    "InventoryObserved",
    "InventoryService",
    "InventorySpecState",
    "Product",
    "ProductNotFoundError",
    "ReleaseArgs",
    "ReleaseExceedsReservedError",
    "ReleaseReceipt",
    "ReservationReceipt",
    "ReserveArgs",
    "RestockArgs",
    "RestockReceipt",
    "SimulatedFaultError",
    "build_release_witness",
    "build_reserve_witness",
    "build_restock_witness",
    "release_contract",
    "release_runner",
    "reserve_contract",
    "reserve_runner",
    "restock_contract",
    "restock_runner",
]
