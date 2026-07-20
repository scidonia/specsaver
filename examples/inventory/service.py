"""Inventory service — SQLite-backed implementation.

Three operations share one products table:

  - reserve  — move quantity from available to reserved (order placed)
  - release  — move quantity from reserved back to available (order cancelled)
  - restock  — add quantity to on_hand (shipment received)

The contracts live in contract.py as standalone Contract objects.
The @contract decorator is *not* used here: it auto-discovers a single
implementation method, which does not scale to multi-operation classes.
"""

from __future__ import annotations

import sqlite3 as _sqlite3

from examples.inventory.types import (
    InsufficientStockError,
    ProductNotFoundError,
    ReleaseExceedsReservedError,
    ReleaseReceipt,
    ReservationReceipt,
    RestockReceipt,
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
        db_path: str,
        sku: str,
        order_id: str,
        quantity: int,
    ) -> ReservationReceipt:
        """Spilled-out argument list — domain adapter unpacks ReserveArgs."""
        with _sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN")

            row = conn.execute(
                "SELECT on_hand, reserved, reorder_point"
                " FROM products WHERE sku = ?",
                (sku,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise ProductNotFoundError(
                    sku, order_id, quantity,
                    f"Product {sku!r} not found",
                )

            on_hand, reserved, _reorder_point = row
            available = on_hand - reserved

            if available < quantity:
                conn.execute("ROLLBACK")
                raise InsufficientStockError(
                    sku, order_id, quantity, available,
                    f"Available {available} < quantity {quantity}",
                )

            conn.execute(
                "UPDATE products SET reserved = reserved + ? WHERE sku = ?",
                (quantity, sku),
            )
            conn.execute("COMMIT")

            return ReservationReceipt(
                reservation_id=self._next_id("rsv"),
                sku=sku,
                order_id=order_id,
                quantity=quantity,
            )

    def release(
        self,
        db_path: str,
        sku: str,
        order_id: str,
        quantity: int,
    ) -> ReleaseReceipt:
        with _sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN")

            row = conn.execute(
                "SELECT on_hand, reserved, reorder_point"
                " FROM products WHERE sku = ?",
                (sku,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise ProductNotFoundError(
                    sku, order_id, quantity,
                    f"Product {sku!r} not found",
                )

            _on_hand, reserved, _reorder_point = row

            if reserved < quantity:
                conn.execute("ROLLBACK")
                raise ReleaseExceedsReservedError(
                    sku, order_id, quantity, reserved,
                    f"Reserved {reserved} < release quantity {quantity}",
                )

            conn.execute(
                "UPDATE products SET reserved = reserved - ? WHERE sku = ?",
                (quantity, sku),
            )
            conn.execute("COMMIT")

            return ReleaseReceipt(
                sku=sku,
                order_id=order_id,
                quantity=quantity,
            )

    def restock(
        self,
        db_path: str,
        sku: str,
        quantity: int,
    ) -> RestockReceipt:
        with _sqlite3.connect(db_path) as conn:
            conn.execute("BEGIN")

            row = conn.execute(
                "SELECT on_hand FROM products WHERE sku = ?",
                (sku,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise ProductNotFoundError(
                    sku, "", quantity,
                    f"Product {sku!r} not found",
                )

            conn.execute(
                "UPDATE products SET on_hand = on_hand + ? WHERE sku = ?",
                (quantity, sku),
            )
            conn.execute("COMMIT")

            return RestockReceipt(
                receipt_id=self._next_id("stk"),
                sku=sku,
                quantity=quantity,
            )
