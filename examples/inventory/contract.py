"""Inventory — contracts for three operations sharing one state.

The frame conditions are *semantic*: the runner checks that everything
outside a contract's ``writes`` (or an exit's ``writes``) is unchanged,
and that derived fields agree with ``derives``.  Only the essential spec
remains below:

  - **deltas** (what must change, and by how much)
  - **event content** (extends_by_one with exact fields)
  - **conditional emission** (an alert iff the reorder point is crossed)

Conservation, frame preservation, post-state legality (the invariant is
checked on the post-state), derived deltas, and "all other channels
silent" are generated, not stated.

Shared domain properties — the invariant, derivations, state schema, and
ghost machinery — belong to the state, not to any one operation.  They
are factored as shared locals below (a future DomainSpec would own them).
"""

from examples.inventory.projection import InventoryProjection
from examples.inventory.service import InventoryService
from examples.inventory.types import (
    InsufficientStockError,
    InventoryGhost,
    ReleaseArgs,
    ReleaseExceedsReservedError,
    ReserveArgs,
    RestockArgs,
)
from specsaver.contract_model import Contract, ExcExit, StateField
from specsaver.logic import extends_by_one, implies

_projection = InventoryProjection()


def _available(state, sku: str) -> int:
    p = state.observed.products[sku]
    return p.on_hand - p.reserved


def _crossed_reorder_point(old_s, args, new_s) -> bool:
    """Available stock moved from above the reorder point to at-or-below it."""
    rp = old_s.observed.products[args.sku].reorder_point
    return _available(old_s, args.sku) > rp >= _available(new_s, args.sku)


def _gauge_reflects_state(g, args, new_s) -> bool:
    p = new_s.observed.products[args.sku]
    return (
        g.sku == args.sku
        and g.on_hand == p.on_hand
        and g.reserved == p.reserved
        and g.available == p.on_hand - p.reserved
    )


# ---------------------------------------------------------------------------
# Shared domain properties (state-level, not per-operation)
# ---------------------------------------------------------------------------


def _invariant_stock_legal(state) -> bool:
    return all(
        p.on_hand >= 0 and p.reserved >= 0 and p.reserved <= p.on_hand
        for p in state.observed.products.values()
    )


_DERIVES = {
    "total_on_hand": lambda state: sum(
        p.on_hand for p in state.observed.products.values()
    ),
    "total_reserved": lambda state: sum(
        p.reserved for p in state.observed.products.values()
    ),
    "total_available": lambda state: sum(
        p.on_hand - p.reserved for p in state.observed.products.values()
    ),
}

_STATE_SCHEMA = {
    "products": StateField(
        type_hint="Mapping[str, Product]", provenance="observed",
    ),
    "reservation_log": StateField(
        type_hint="tuple[StockReserved, ...]", provenance="observed",
    ),
    "gauge_log": StateField(
        type_hint="tuple[StockLevelGauge, ...]", provenance="observed",
    ),
    "alert_log": StateField(
        type_hint="tuple[LowStockAlert, ...]", provenance="observed",
    ),
    "failure_log": StateField(
        type_hint="tuple[ReservationFailed, ...]", provenance="observed",
    ),
    "release_log": StateField(
        type_hint="tuple[ReservationReleased, ...]", provenance="observed",
    ),
    "release_failure_log": StateField(
        type_hint="tuple[ReleaseFailed, ...]", provenance="observed",
    ),
    "restock_log": StateField(
        type_hint="tuple[StockReceived, ...]", provenance="observed",
    ),
    "total_on_hand": StateField(type_hint="int", provenance="derived"),
    "total_reserved": StateField(type_hint="int", provenance="derived"),
    "total_available": StateField(type_hint="int", provenance="derived"),
    "initial_total_on_hand": StateField(
        type_hint="int", provenance="ghost",
    ),
}

def _ghost_init(witness) -> InventoryGhost:
    return InventoryGhost(
        initial_total_on_hand=sum(
            p.on_hand for p in witness["products"].values()
        )
    )


_GHOST_TRANSITIONS = [
    lambda old_g, args, result, new_g: (
        old_g.initial_total_on_hand == new_g.initial_total_on_hand
    ),
]

_GHOST_INVARIANTS = [
    lambda state: state.ghost.initial_total_on_hand is not None,
]


reserve_contract = Contract(
    InventoryService.reserve,
    args_type=ReserveArgs,
    feature="reserve.feature",
    when='stock of <quantity> is reserved for order "<order>" on "<sku>"',
    observe=_projection.snapshot,
    requires=[
        lambda state, args: args.quantity > 0,
        lambda state, args: args.sku in state.observed.products,
    ],
    ensures=[
        # --- the delta ------------------------------------------------
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
        # --- telemetry: an alert iff the reorder point was crossed ----
        lambda old_s, args, result, new_s: implies(
            _crossed_reorder_point(old_s, args, new_s),
            extends_by_one(
                old_s.observed.alert_log, new_s.observed.alert_log,
                lambda a: (
                    a.sku == args.sku
                    and a.available == _available(new_s, args.sku)
                    and a.reorder_point
                    == new_s.observed.products[args.sku].reorder_point
                ),
            ),
        ),
        lambda old_s, args, result, new_s: implies(
            not _crossed_reorder_point(old_s, args, new_s),
            new_s.observed.alert_log == old_s.observed.alert_log,
        ),
    ],
    exceptions=[
        ExcExit(
            raises=InsufficientStockError,
            when=[
                lambda state, args: (
                    state.observed.products[args.sku].on_hand
                    - state.observed.products[args.sku].reserved
                    < args.quantity
                ),
            ],
            writes={"state.failure_log"},
            ensures=[
                # --- exactly one failure counter, exact fields --------
                lambda state, args, exc, after_s: extends_by_one(
                    state.observed.failure_log, after_s.observed.failure_log,
                    lambda f: (
                        f.sku == args.sku
                        and f.order_id == args.order_id
                        and f.quantity == args.quantity
                        and f.available == exc.available
                        and f.reason == InsufficientStockError.code
                    ),
                ),
                # --- exception payload matches the call ---------------
                lambda state, args, exc, after_s: exc.sku == args.sku,
                lambda state, args, exc, after_s: (
                    exc.order_id == args.order_id
                ),
                lambda state, args, exc, after_s: (
                    exc.quantity == args.quantity
                ),
                lambda state, args, exc, after_s: (
                    exc.available
                    == state.observed.products[args.sku].on_hand
                    - state.observed.products[args.sku].reserved
                ),
            ],
        ),
    ],
    invariants=[_invariant_stock_legal],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=InventoryGhost,
    ghost_init=_ghost_init,
    ghost_transitions=_GHOST_TRANSITIONS,
    ghost_invariants=_GHOST_INVARIANTS,
    writes={
        "state.products[sku].reserved",
        "state.reservation_log",
        "state.gauge_log",
        "state.alert_log",
    },
    reads={
        "state.products[sku].on_hand",
        "state.products[sku].reserved",
        "state.products[sku].reorder_point",
    },
)


release_contract = Contract(
    InventoryService.release,
    args_type=ReleaseArgs,
    feature="release.feature",
    when='stock of <quantity> is released for order "<order>" on "<sku>"',
    observe=_projection.snapshot,
    requires=[
        lambda state, args: args.quantity > 0,
        lambda state, args: args.sku in state.observed.products,
    ],
    ensures=[
        # --- the delta ------------------------------------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.products[args.sku].reserved
            == old_s.observed.products[args.sku].reserved - args.quantity
        ),
        # --- telemetry: domain event, exact fields --------------------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.release_log, new_s.observed.release_log,
            lambda e: (
                e.sku == args.sku
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
    exceptions=[
        ExcExit(
            raises=ReleaseExceedsReservedError,
            when=[
                lambda state, args: (
                    state.observed.products[args.sku].reserved
                    < args.quantity
                ),
            ],
            writes={"state.release_failure_log"},
            ensures=[
                # --- exactly one failure counter, exact fields --------
                lambda state, args, exc, after_s: extends_by_one(
                    state.observed.release_failure_log,
                    after_s.observed.release_failure_log,
                    lambda f: (
                        f.sku == args.sku
                        and f.order_id == args.order_id
                        and f.quantity == args.quantity
                        and f.reserved == exc.reserved
                        and f.reason == ReleaseExceedsReservedError.code
                    ),
                ),
                # --- exception payload matches the call ---------------
                lambda state, args, exc, after_s: exc.sku == args.sku,
                lambda state, args, exc, after_s: (
                    exc.order_id == args.order_id
                ),
                lambda state, args, exc, after_s: (
                    exc.quantity == args.quantity
                ),
                lambda state, args, exc, after_s: (
                    exc.reserved
                    == state.observed.products[args.sku].reserved
                ),
            ],
        ),
    ],
    invariants=[_invariant_stock_legal],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=InventoryGhost,
    ghost_init=_ghost_init,
    ghost_transitions=_GHOST_TRANSITIONS,
    ghost_invariants=_GHOST_INVARIANTS,
    writes={
        "state.products[sku].reserved",
        "state.release_log",
        "state.gauge_log",
    },
    reads={
        "state.products[sku].reserved",
        "state.products[sku].on_hand",
    },
)


restock_contract = Contract(
    InventoryService.restock,
    args_type=RestockArgs,
    feature="restock.feature",
    when='stock of <quantity> is received on "<sku>"',
    observe=_projection.snapshot,
    requires=[
        lambda state, args: args.quantity > 0,
        lambda state, args: args.sku in state.observed.products,
    ],
    ensures=[
        # --- the delta ------------------------------------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.products[args.sku].on_hand
            == old_s.observed.products[args.sku].on_hand + args.quantity
        ),
        # --- telemetry: domain event, exact fields --------------------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.restock_log, new_s.observed.restock_log,
            lambda e: e.sku == args.sku and e.quantity == args.quantity,
        ),
        # --- telemetry: gauge must reflect the actual post-state ------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.gauge_log, new_s.observed.gauge_log,
            lambda g: _gauge_reflects_state(g, args, new_s),
        ),
    ],
    invariants=[_invariant_stock_legal],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=InventoryGhost,
    ghost_init=_ghost_init,
    ghost_transitions=_GHOST_TRANSITIONS,
    ghost_invariants=_GHOST_INVARIANTS,
    writes={
        "state.products[sku].on_hand",
        "state.restock_log",
        "state.gauge_log",
    },
    reads={
        "state.products[sku].on_hand",
    },
)
