"""Unguarded reserve implementation — yields failure witnesses at runtime.

``reserve_unguarded`` is the reserve operation WITHOUT the
``InsufficientStockError`` guard.  Unlike the false contract
(``contract_false.py``, which keeps the guarded implementation and
only breaks the spec), this implementation itself is broken: it
writes ``reserved`` above ``on_hand``, so the post-state violates
the stock invariant directly.

Running the scenario runner on this implementation with insufficient
stock produces the counter-example *from the implementation's own
behavior* — no hand-authored witness.  ``discover_witness`` captures
that failure in runner-JSON form for ``emit_layered
(counter_witnesses=...)`` / ``gen_obligations.py --counter``.

This is the scenario-discovered witness path of
docs/proof-counterexample-workflow.md §7.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from examples.inventory.contract import (
    ReserveArgs,
    _invariant_stock_legal,
)
from examples.inventory.events import (  # noqa: F401
    LowStockAlert,
    StockLevelGauge,
    StockReserved,
)
from examples.inventory.projection import (
    build_reserve_witness,
)
from examples.inventory.types import ReservationReceipt
from specsaver.contract_model import Contract

_SELECT_PRODUCT = text(
    "SELECT on_hand, reserved, reorder_point FROM products WHERE sku = :sku"
)


class UnguardedInventoryService:
    """Reserve WITHOUT the availability check — the broken implementation."""

    def reserve(
        self,
        engine: Engine,
        sku: str,
        order_id: str,
        quantity: int,
    ) -> ReservationReceipt:
        with engine.begin() as conn:
            row = conn.execute(_SELECT_PRODUCT, {"sku": sku}).fetchone()
            if row is None:
                raise KeyError(sku)
            on_hand, reserved, reorder_point = row

            # NO guard: available = on_hand - reserved may be < quantity.
            conn.execute(
                text("UPDATE products SET reserved = reserved + :qty"
                     " WHERE sku = :sku"),
                {"qty": quantity, "sku": sku},
            )
        return ReservationReceipt(
            reservation_id=f"res-{order_id}-{sku}",
            sku=sku,
            order_id=order_id,
            quantity=quantity,
        )


reserve_unguarded_contract = Contract(
    UnguardedInventoryService().reserve,
    args_type=ReserveArgs,
    feature="reserve.feature",
    when='stock of <quantity> is reserved for order "<order>" on "<sku>"',
    requires=[
        lambda state, args: args.quantity > 0,
        lambda state, args: args.sku in state.observed.products,
    ],
    ensures=[
        lambda old_s, args, result, new_s: (
            new_s.observed.products[args.sku].reserved
            == old_s.observed.products[args.sku].reserved + args.quantity
        ),
    ],
    exceptions=[],
    invariants=[_invariant_stock_legal],
)


class _UnguardedImpl:
    """Runner impl wrapper for the unguarded service."""

    def __init__(self) -> None:
        self._svc = UnguardedInventoryService()

    def execute(self, context, args):
        return self._svc.reserve(
            context.engine, args.sku, args.order_id, args.quantity
        )


def discover_witness(row: dict[str, str]) -> dict | None:
    """Drive the unguarded implementation on one context; if it breaks
    the stock invariant, return the counter-example in runner-JSON form
    (for emit_layered counter_witnesses / gen_obligations --counter).

    Returns None if the row does not produce a violation.
    """
    from examples.inventory.projection import (
        InventoryMaterializer,
        InventoryProjection,
    )
    witness = build_reserve_witness(row)
    materializer = InventoryMaterializer()
    projection = InventoryProjection()
    context = materializer.materialize(witness)
    before = projection.snapshot(context)

    # Invariant must hold before, and the contract's requires must pass.
    if not all(inv(before) for inv in reserve_unguarded_contract.invariants):
        return None
    if not all(p(before, witness.args)
               for p in reserve_unguarded_contract.requires):
        return None

    impl = _UnguardedImpl()
    try:
        impl.execute(context, witness.args)
    except Exception:
        return None  # implementation raised — a different witness kind

    after = projection.snapshot(context)
    violated = [inv for inv in reserve_unguarded_contract.invariants
                if not inv(after)]
    if not violated:
        return None

    # The implementation broke the invariant.  Package the witness.
    store = {
        sku: {
            "on_hand": p.on_hand,
            "reserved": p.reserved,
            "reorder_point": p.reorder_point,
        }
        for sku, p in before.observed.products.items()
    }
    computed = {}
    for sku, p in after.observed.products.items():
        b = before.observed.products[sku]
        if p.reserved != b.reserved or p.on_hand != b.on_hand:
            computed[sku] = {
                "on_hand": p.on_hand,
                "reserved": p.reserved,
                "reorder_point": p.reorder_point,
            }
    return {
        "obligation": "o5_invariant_preservation",
        "store": store,
        "args": [row["sku"], row["order"], int(row["quantity"])],
        "computed": computed.get(row["sku"], computed),
        "runtime_message": "invariant failed after",
    }


# The canonical failing row for the demo:
#   on_hand 10, reserved 8, qty 5 → reserved' = 13 > on_hand 10.
FAILING_ROW = {
    "sku": "SKU1",
    "order": "ORDER1",
    "quantity": "5",
    "on_hand": "10",
    "reserved": "8",
    "reorder_point": "5",
    "outcome": "success",
}

# Canonical witness from FAILING_ROW: reserved 8→13 > on_hand 10.
UNGUARDED_RESERVE_WITNESS = discover_witness(FAILING_ROW)
