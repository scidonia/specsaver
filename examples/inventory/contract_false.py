"""Deliberately FALSE contract — regression test for the DISPROVED path.

``reserve_no_guard_contract`` is the reserve contract with the
``InsufficientStockError`` exception arm removed.  The availability
check disappears from ``gen_pre``, so the update can drive
``reserved`` above ``on_hand``, breaking the
``reserved <= on_hand`` invariant.

The canonical counter-example:

    store: SKU1 -> {on_hand: 10, reserved: 8, reorder_point: 5}
    args:  reserve("SKU1", "ORDER1", 5)
    post:  reserved' = 8 + 5 = 13 > 10 = on_hand   (invariant violated)

This witness is materialized into ``reserve_no_guard_Lneg.v`` by
``scripts/gen_obligations.py --counter`` (or ``emit_layered`` with
``counter_witnesses``), and certified by rocq-piler as a DISPROVED
verdict on invariant preservation.  See
docs/proof-counterexample-workflow.md.
"""

from __future__ import annotations

from examples.inventory.contract import (
    InventoryService,
    ReserveArgs,
    _gauge_reflects_state,
    _invariant_stock_legal,
    extends_by_one,
)
from examples.inventory.service import InsufficientStockError  # noqa: F401
from specsaver.contract_model import Contract


def reserve_no_guard(self, engine, sku, order_id, quantity):
    """Unguarded reserve — the implementation for the false contract.

    Identical call-through to the real reserve; the falsity lives in
    the SPECIFICATION (no InsufficientStockError arm), not the code.
    The distinct __name__ gives the false contract its own emission
    directory (coq/gen/reserve_no_guard/).
    """
    return InventoryService.reserve(self, engine, sku, order_id, quantity)


reserve_no_guard_contract = Contract(
    reserve_no_guard,
    args_type=ReserveArgs,
    feature="reserve.feature",
    when='stock of <quantity> is reserved for order "<order>" on "<sku>"',
    requires=[
        lambda state, args: args.quantity > 0,
        lambda state, args: args.sku in state.observed.products,
    ],
    ensures=[
        # --- the delta (same as the true contract) -------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.products[args.sku].reserved
            == old_s.observed.products[args.sku].reserved + args.quantity
        ),
        # --- telemetry: domain event, exact fields --------------------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.reservation_log, new_s.observed.reservation_log,
            lambda e: (
                e.reservation_id == result.reservation_id
                and e.sku == args.sku
                and e.order_id == args.order_id
                and e.quantity == args.quantity
            ),
        ),
        # --- telemetry: gauge must reflect the actual post-state ------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.gauge_log, new_s.observed.gauge_log,
            lambda g: _gauge_reflects_state(g, args, new_s),
        ),
    ],
    # NO exceptions — the InsufficientStockError arm is missing.
    # This is the specification bug: nothing stops reserved > on_hand.
    exceptions=[],
    # The invariant is PRESENT — that's the point.  The bug is that no
    # exception arm guards it, so the update can violate it.
    invariants=[_invariant_stock_legal],
)


# The canonical witness for the DISPROVED verdict, in runner-JSON form.
FALSE_RESERVE_WITNESS = {
    "obligation": "invariant_preservation",
    "store": {"SKU1": {"on_hand": 10, "reserved": 8, "reorder_point": 5}},
    "args": ["SKU1", "ORDER1", 5],
    "computed": {"on_hand": 10, "reserved": 13, "reorder_point": 5},
}
