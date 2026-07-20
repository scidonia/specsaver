"""Projection and refinement bridge for the inventory domain.

This module is the coupling layer between the concrete execution world
(SQLite database) and the abstract specification state (InventorySpecState).

Symmetric architecture:
  - materialize(witness) → ExecutionContext  (write abstract → concrete)
  - snapshot(context) → SpecState            (read concrete → abstract)

The same snapshot is used before AND after execution (symmetry requirement).

Exports ``InventoryScenarioRunner`` — the single entry point that bundles
all domain-specific wiring (witness builder, materializer, projection, impl).
Both the CLI (``--verify`` / ``--pre-only``) and pytest tests consume it.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from typing import Any

from examples.inventory.events import (
    EventLog,
    LowStockAlert,
    ReleaseFailed,
    ReservationFailed,
    ReservationReleased,
    StockLevelGauge,
    StockReceived,
    StockReserved,
)
from examples.inventory.types import (
    InsufficientStockError,
    InventoryDerived,
    InventoryGhost,
    InventoryObserved,
    InventorySpecState,
    Product,
    ReleaseArgs,
    ReleaseExceedsReservedError,
    ReserveArgs,
    RestockArgs,
    SimulatedFaultError,
)
from specsaver.scenario_runner import ScenarioRunner

# ---------------------------------------------------------------------------
# ExecutionContext — the concrete execution world
# ---------------------------------------------------------------------------


@dataclass
class InventoryExecutionContext:
    """The concrete world the implementation operates on."""

    db_path: str
    events: EventLog = field(default_factory=EventLog)
    ghost: InventoryGhost = field(default_factory=InventoryGhost)


# ---------------------------------------------------------------------------
# ScenarioWitness — abstract initial state + args from a Gherkin row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InventoryScenarioWitness:
    """Produced from a Gherkin Examples row by a build_*_witness function."""

    products: dict[str, Product]
    args: ReserveArgs | ReleaseArgs | RestockArgs
    ghost: InventoryGhost = field(default_factory=InventoryGhost)


# ---------------------------------------------------------------------------
# Database schema helpers
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL,
    reserved INTEGER NOT NULL,
    reorder_point INTEGER NOT NULL
);
"""


def _populate(conn: sqlite3.Connection, products: dict[str, Product]) -> None:
    conn.execute("DELETE FROM products")
    for p in products.values():
        conn.execute(
            "INSERT INTO products (sku, on_hand, reserved, reorder_point)"
            " VALUES (?, ?, ?, ?)",
            (p.sku, p.on_hand, p.reserved, p.reorder_point),
        )
    conn.commit()


def _read_product(db_path: str, sku: str) -> Product | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sku, on_hand, reserved, reorder_point"
            " FROM products WHERE sku = ?",
            (sku,),
        ).fetchone()
    if row is None:
        return None
    return Product(sku=row[0], on_hand=row[1], reserved=row[2],
                   reorder_point=row[3])


# ---------------------------------------------------------------------------
# Materializer — witness → ExecutionContext
# ---------------------------------------------------------------------------


class InventoryMaterializer:
    """Creates a concrete ExecutionContext (temp SQLite DB) from a witness."""

    def materialize(
        self, witness: InventoryScenarioWitness
    ) -> InventoryExecutionContext:
        fd, path = tempfile.mkstemp(suffix=".db", prefix="specsaver_inv_")
        os.close(fd)
        with sqlite3.connect(path) as conn:
            conn.executescript(_SCHEMA)
            _populate(conn, witness.products)
        return InventoryExecutionContext(
            db_path=path,
            events=EventLog(),
            ghost=witness.ghost,
        )


# ---------------------------------------------------------------------------
# Projection — ExecutionContext → immutable SpecState (symmetric)
# ---------------------------------------------------------------------------


class InventoryProjection:
    """Projects the execution context into an immutable SpecState.

    Used symmetrically: before execution (pre-state) and after execution
    (post-state).  Same function, same schema, same interpretation.
    """

    def snapshot(self, context: InventoryExecutionContext) -> InventorySpecState:
        with sqlite3.connect(context.db_path) as conn:
            product_rows = conn.execute(
                "SELECT sku, on_hand, reserved, reorder_point FROM products"
            ).fetchall()

        products: dict[str, Product] = {
            row[0]: Product(sku=row[0], on_hand=row[1], reserved=row[2],
                            reorder_point=row[3])
            for row in product_rows
        }

        records = context.events._records
        observed = InventoryObserved(
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
        derived = InventoryDerived(
            total_on_hand=sum(p.on_hand for p in products.values()),
            total_reserved=sum(p.reserved for p in products.values()),
            total_available=sum(
                p.on_hand - p.reserved for p in products.values()
            ),
        )

        ghost = InventoryGhost(
            initial_total_on_hand=context.ghost.initial_total_on_hand
        )

        return InventorySpecState(
            observed=observed,
            derived=derived,
            ghost=ghost,
        )


# ---------------------------------------------------------------------------
# Witness builder — Gherkin Examples row → ScenarioWitness
# ---------------------------------------------------------------------------


def _build_products(row: dict[str, str]) -> dict[str, Product]:
    products: dict[str, Product] = {}
    if row.get("on_hand"):
        products[row["sku"]] = Product(
            sku=row["sku"],
            on_hand=int(row["on_hand"]),
            reserved=int(row["reserved"]),
            reorder_point=int(row["reorder_point"]),
        )
    return products


def build_reserve_witness(row: dict[str, str]) -> InventoryScenarioWitness:
    """Map a reserve.feature Examples row to a ScenarioWitness."""
    return InventoryScenarioWitness(
        products=_build_products(row),
        args=ReserveArgs(
            sku=row["sku"], order_id=row["order"],
            quantity=int(row["quantity"]),
        ),
    )


def build_release_witness(row: dict[str, str]) -> InventoryScenarioWitness:
    """Map a release.feature Examples row to a ScenarioWitness."""
    return InventoryScenarioWitness(
        products=_build_products(row),
        args=ReleaseArgs(
            sku=row["sku"], order_id=row["order"],
            quantity=int(row["quantity"]),
        ),
    )


def build_restock_witness(row: dict[str, str]) -> InventoryScenarioWitness:
    """Map a restock.feature Examples row to a ScenarioWitness."""
    return InventoryScenarioWitness(
        products=_build_products(row),
        args=RestockArgs(
            sku=row["sku"], quantity=int(row["quantity"]),
        ),
    )


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def cleanup(context: InventoryExecutionContext) -> None:
    """Remove the temp database after a test."""
    if os.path.exists(context.db_path):
        os.unlink(context.db_path)


# ---------------------------------------------------------------------------
# Scenario runner — single export that bundles all domain wiring
# ---------------------------------------------------------------------------
# Both the CLI (--verify / --pre-only) and pytest tests consume this
# runner, so the wiring lives in exactly one place per domain.


class _FaultState:
    def __init__(self) -> None:
        self.pending: str | None = None

    def inject(self, fault_name: str) -> None:
        self.pending = fault_name

    def consume(self) -> str | None:
        f = self.pending
        self.pending = None
        return f


class _FaultableReserveService:
    """Reserve under contract: service + telemetry emission.

    Emits on the success path:
      - StockReserved (domain event)
      - StockLevelGauge (absolute levels, post-state)
      - LowStockAlert, edge-triggered: only when available stock crosses
        from above the reorder point to at-or-below it

    Emits on the insufficient-stock path:
      - ReservationFailed (counter), and no success telemetry
    """

    def __init__(self, inner: Any = None) -> None:
        from examples.inventory.service import InventoryService

        self._inner = inner or InventoryService()

    def inject_fault(self, fault_name: str) -> None:
        _fault_state.inject(fault_name)

    def execute(self, context, args):
        fault = _fault_state.consume()
        if fault == "simulated_fault":
            raise SimulatedFaultError(
                sku=args.sku,
                order_id=args.order_id,
                quantity=args.quantity,
                message="Simulated runtime fault",
            )

        before = _read_product(context.db_path, args.sku)
        try:
            result = self._inner.reserve(
                context.db_path, args.sku, args.order_id, args.quantity
            )
        except InsufficientStockError as exc:
            context.events.emit(
                "failure",
                ReservationFailed(
                    sku=args.sku,
                    order_id=args.order_id,
                    quantity=args.quantity,
                    available=exc.available,
                    reason=InsufficientStockError.code,
                ),
            )
            raise

        after = _read_product(context.db_path, args.sku)
        assert after is not None  # product exists: reserve succeeded

        context.events.emit(
            "reservation",
            StockReserved(
                reservation_id=result.reservation_id,
                sku=args.sku,
                order_id=args.order_id,
                quantity=args.quantity,
            ),
        )
        context.events.emit(
            "gauge",
            StockLevelGauge(
                sku=args.sku,
                on_hand=after.on_hand,
                reserved=after.reserved,
                available=after.on_hand - after.reserved,
            ),
        )

        before_available = (
            before.on_hand - before.reserved if before is not None else None
        )
        after_available = after.on_hand - after.reserved
        if (
            before_available is not None
            and before_available > after.reorder_point
            and after_available <= after.reorder_point
        ):
            context.events.emit(
                "alert",
                LowStockAlert(
                    sku=args.sku,
                    available=after_available,
                    reorder_point=after.reorder_point,
                ),
            )

        return result


class _FaultableReleaseService:
    """Release under contract: service + telemetry emission.

    Releases can only raise availability, so no LowStockAlert is ever
    emitted.  On over-release: exactly one ReleaseFailed, no success
    telemetry.
    """

    def __init__(self, inner: Any = None) -> None:
        from examples.inventory.service import InventoryService

        self._inner = inner or InventoryService()

    def inject_fault(self, fault_name: str) -> None:
        _fault_state.inject(fault_name)

    def execute(self, context, args):
        fault = _fault_state.consume()
        if fault == "simulated_fault":
            raise SimulatedFaultError(
                sku=args.sku,
                order_id=args.order_id,
                quantity=args.quantity,
                message="Simulated runtime fault",
            )

        try:
            result = self._inner.release(
                context.db_path, args.sku, args.order_id, args.quantity
            )
        except ReleaseExceedsReservedError as exc:
            context.events.emit(
                "release_failure",
                ReleaseFailed(
                    sku=args.sku,
                    order_id=args.order_id,
                    quantity=args.quantity,
                    reserved=exc.reserved,
                    reason=ReleaseExceedsReservedError.code,
                ),
            )
            raise

        after = _read_product(context.db_path, args.sku)
        assert after is not None

        context.events.emit(
            "release",
            ReservationReleased(
                sku=args.sku,
                order_id=args.order_id,
                quantity=args.quantity,
            ),
        )
        context.events.emit(
            "gauge",
            StockLevelGauge(
                sku=args.sku,
                on_hand=after.on_hand,
                reserved=after.reserved,
                available=after.on_hand - after.reserved,
            ),
        )
        return result


class _RestockService:
    """Restock under contract: service + telemetry emission."""

    def __init__(self, inner: Any = None) -> None:
        from examples.inventory.service import InventoryService

        self._inner = inner or InventoryService()

    def execute(self, context, args):
        result = self._inner.restock(
            context.db_path, args.sku, args.quantity
        )

        after = _read_product(context.db_path, args.sku)
        assert after is not None

        context.events.emit(
            "restock",
            StockReceived(sku=args.sku, quantity=args.quantity),
        )
        context.events.emit(
            "gauge",
            StockLevelGauge(
                sku=args.sku,
                on_hand=after.on_hand,
                reserved=after.reserved,
                available=after.on_hand - after.reserved,
            ),
        )
        return result


_fault_state = _FaultState()


class InventoryScenarioRunner(ScenarioRunner):
    """Bundles the inventory wiring needed to run a scenario for ONE operation.

    Thin domain wrapper over the generic specsaver ScenarioRunner:
    supplies the inventory materializer, projection, and cleanup; the
    operation supplies the contract, impl wrapper, and witness builder.
    """

    def __init__(self, contract, impl, witness_builder) -> None:
        super().__init__(
            contract,
            materializer=InventoryMaterializer(),
            projection=InventoryProjection(),
            impl=impl,
            witness_builder=witness_builder,
            cleanup=cleanup,
        )
