"""Inventory example — Gherkin → Contracts → Implementation."""

from examples.inventory.contract import (
    release_contract,
    reserve_contract,
    restock_contract,
)
from examples.inventory.projection import (
    InventoryExecutionContext,
    InventoryScenarioRunner,
    InventoryScenarioWitness,
    _FaultableReleaseService,
    _FaultableReserveService,
    _RestockService,
    build_release_witness,
    build_reserve_witness,
    build_restock_witness,
    cleanup,
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

# One runner per operation — each bundles its contract, effect-emitting
# impl wrapper, and witness builder.  Consumed by CLI (--verify) and tests.
reserve_runner = InventoryScenarioRunner(
    reserve_contract, _FaultableReserveService(), build_reserve_witness,
)
release_runner = InventoryScenarioRunner(
    release_contract, _FaultableReleaseService(), build_release_witness,
)
restock_runner = InventoryScenarioRunner(
    restock_contract, _RestockService(), build_restock_witness,
)


def _verify_reserve(row, pre_only=False):
    return reserve_runner.check_pre(row) if pre_only else reserve_runner.run(row)


def _verify_release(row, pre_only=False):
    return release_runner.check_pre(row) if pre_only else release_runner.run(row)


def _verify_restock(row, pre_only=False):
    return restock_runner.check_pre(row) if pre_only else restock_runner.run(row)


__verify_runner__ = {
    "reserve.feature": _verify_reserve,
    "release.feature": _verify_release,
    "restock.feature": _verify_restock,
}

__all__ = [
    "FEATURE",
    "InsufficientStockError",
    "InventoryDerived",
    "InventoryError",
    "InventoryExecutionContext",
    "InventoryGhost",
    "InventoryObserved",
    "InventoryScenarioRunner",
    "InventoryScenarioWitness",
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
    "cleanup",
    "release_contract",
    "release_runner",
    "reserve_contract",
    "reserve_runner",
    "restock_contract",
    "restock_runner",
]
