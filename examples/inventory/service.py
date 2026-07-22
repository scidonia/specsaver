"""Inventory service — SQLite-backed implementation via SQLAlchemy.

Three operations share one products table:

  - reserve  — move quantity from available to reserved (order placed)
  - release  — move quantity from reserved back to available (order cancelled)
  - restock  — add quantity to on_hand (shipment received)

The contracts live in contract.py as standalone Contract objects.
The @contract decorator is *not* used here: it auto-discovers a single
implementation method, which does not scale to multi-operation classes.

The service works against any SQLAlchemy engine — a real SQLite file in
production, or the theory's stub engine (``specsaver.theory.sql``) under
verification.  ``engine.begin()`` gives commit-on-success /
rollback-on-exception for free.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from examples.inventory.types import (
    InsufficientStockError,
    ProductNotFoundError,
    ReleaseExceedsReservedError,
    ReleaseReceipt,
    ReservationReceipt,
    RestockReceipt,
)

_SELECT_PRODUCT = text(
    "SELECT on_hand, reserved, reorder_point FROM products WHERE sku = :sku"
)


class InventoryService:
    """Implementation — contracts are attached externally."""

    _counter: int = 0

    @classmethod
    def _next_id(cls, prefix: str) -> str:
        cls._counter += 1
        return f"{prefix}-{cls._counter:06d}"

    def reserve(
        self,
        engine: Engine,
        sku: str,
        order_id: str,
        quantity: int,
    ) -> ReservationReceipt:
        """Spilled-out argument list — domain adapter unpacks ReserveArgs."""
        with engine.begin() as conn:
            row = conn.execute(_SELECT_PRODUCT, {"sku": sku}).fetchone()
            if row is None:
                raise ProductNotFoundError(
                    sku, order_id, quantity,
                    f"Product {sku!r} not found",
                )

            on_hand, reserved, _reorder_point = row
            available = on_hand - reserved

            if available < quantity:
                raise InsufficientStockError(
                    sku, order_id, quantity, available,
                    f"Available {available} < quantity {quantity}",
                )

            conn.execute(
                text("UPDATE products SET reserved = reserved + :qty"
                     " WHERE sku = :sku"),
                {"qty": quantity, "sku": sku},
            )

        return ReservationReceipt(
            reservation_id=self._next_id("rsv"),
            sku=sku,
            order_id=order_id,
            quantity=quantity,
        )

    def release(
        self,
        engine: Engine,
        sku: str,
        order_id: str,
        quantity: int,
    ) -> ReleaseReceipt:
        with engine.begin() as conn:
            row = conn.execute(_SELECT_PRODUCT, {"sku": sku}).fetchone()
            if row is None:
                raise ProductNotFoundError(
                    sku, order_id, quantity,
                    f"Product {sku!r} not found",
                )

            _on_hand, reserved, _reorder_point = row

            if reserved < quantity:
                raise ReleaseExceedsReservedError(
                    sku, order_id, quantity, reserved,
                    f"Reserved {reserved} < release quantity {quantity}",
                )

            conn.execute(
                text("UPDATE products SET reserved = reserved - :qty"
                     " WHERE sku = :sku"),
                {"qty": quantity, "sku": sku},
            )

        return ReleaseReceipt(
            sku=sku,
            order_id=order_id,
            quantity=quantity,
        )

    def restock(
        self,
        engine: Engine,
        sku: str,
        quantity: int,
    ) -> RestockReceipt:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT on_hand FROM products WHERE sku = :sku"),
                {"sku": sku},
            ).fetchone()
            if row is None:
                raise ProductNotFoundError(
                    sku, "", quantity,
                    f"Product {sku!r} not found",
                )

            conn.execute(
                text("UPDATE products SET on_hand = on_hand + :qty"
                     " WHERE sku = :sku"),
                {"qty": quantity, "sku": sku},
            )

        return RestockReceipt(
            receipt_id=self._next_id("stk"),
            sku=sku,
            quantity=quantity,
        )
