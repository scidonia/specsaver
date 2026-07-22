"""Inventory — SqlDomain declaration (replaces most of projection.py)."""

from examples.inventory.contract import (
    release_contract,
    reserve_contract,
    restock_contract,
)
from examples.inventory.events import (
    LowStockAlert,
    ReleaseFailed,
    ReservationFailed,
    ReservationReleased,
    StockLevelGauge,
    StockReceived,
    StockReserved,
)
from examples.inventory.projection import (
    _FaultableReleaseService,
    _FaultableReserveService,
    _RestockService,
    build_release_witness,
    build_reserve_witness,
    build_restock_witness,
)
from examples.inventory.types import (
    InventoryDerived,
    InventoryGhost,
    InventoryObserved,
    InventorySpecState,
    Product,
)
from specsaver.domain import (
    SqlDomain,
    SqlMaterializer,
    SqlOperation,
    SqlProjection,
    TableSpec,
)

_DDL = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    reorder_point INTEGER NOT NULL
);
"""

_TABLES = (
    TableSpec(
        name="products", key="sku",
        columns=("sku", "on_hand", "reserved", "reorder_point"),
        witness_key="products",
    ),
)


def _extract_observed(context, table_dicts):
    raw = table_dicts["products"]
    products = {
        k: Product(
            sku=k,
            on_hand=v["on_hand"],
            reserved=v["reserved"],
            reorder_point=v["reorder_point"],
        )
        for k, v in raw.items()
    }
    records = context.events._records
    return InventoryObserved(
        products=products,
        reservation_log=tuple(
            e for _, e in records if isinstance(e, StockReserved)
        ),
        gauge_log=tuple(
            e for _, e in records if isinstance(e, StockLevelGauge)
        ),
        alert_log=tuple(
            e for _, e in records if isinstance(e, LowStockAlert)
        ),
        failure_log=tuple(
            e for _, e in records if isinstance(e, ReservationFailed)
        ),
        release_log=tuple(
            e for _, e in records if isinstance(e, ReservationReleased)
        ),
        release_failure_log=tuple(
            e for _, e in records if isinstance(e, ReleaseFailed)
        ),
        restock_log=tuple(
            e for _, e in records if isinstance(e, StockReceived)
        ),
    )


def _compute_derived(observed):
    products = observed.products
    return InventoryDerived(
        total_on_hand=sum(p.on_hand for p in products.values()),
        total_reserved=sum(p.reserved for p in products.values()),
        total_available=sum(
            p.on_hand - p.reserved for p in products.values()
        ),
    )


inventory = SqlDomain(
    name="inventory",
    package="examples.inventory",
    materializer=SqlMaterializer(
        ddl=_DDL,
        tables=_TABLES,
        ghost_init=lambda w: InventoryGhost(
            initial_total_on_hand=sum(
                p.on_hand for p in w.products.values()
            )
        ),
        tempfile_prefix="specsaver_inv_",
    ),
    projection=SqlProjection(
        state_type=InventorySpecState,
        observed_type=InventoryObserved,
        derived_type=InventoryDerived,
        ghost_type=InventoryGhost,
        tables=_TABLES,
        extract_observed=_extract_observed,
        compute_derived=_compute_derived,
    ),
    operations=(
        SqlOperation(
            reserve_contract, _FaultableReserveService(),
            build_reserve_witness, "reserve.feature",
        ),
        SqlOperation(
            release_contract, _FaultableReleaseService(),
            build_release_witness, "release.feature",
        ),
        SqlOperation(
            restock_contract, _RestockService(),
            build_restock_witness, "restock.feature",
        ),
    ),
)
