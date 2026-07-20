"""Telemetry channels — structured output side effects.

Channels are backed by Python's standard :mod:`logging` facility so that
emissions can be captured, mocked, or redirected with standard tools
(``caplog``, ``unittest.mock``, ``logging.config``).

The inventory service issues four kinds of telemetry:

  - ``StockReserved``     — domain event: a reservation succeeded.
  - ``StockLevelGauge``   — telemetry gauge: absolute stock levels after
                            a successful reservation (must reflect the
                            actual post-state — checked by the contract).
  - ``LowStockAlert``     — telemetry alert: edge-triggered when available
                            stock crosses to at-or-below the reorder point.
  - ``ReservationFailed`` — telemetry counter: a reservation was refused
                            (no state change accompanies it).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StockReserved:
    reservation_id: str
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class StockLevelGauge:
    sku: str
    on_hand: int
    reserved: int
    available: int


@dataclass(frozen=True)
class LowStockAlert:
    sku: str
    available: int
    reorder_point: int


@dataclass(frozen=True)
class ReservationFailed:
    sku: str
    order_id: str
    quantity: int
    available: int
    reason: str


@dataclass(frozen=True)
class ReservationReleased:
    sku: str
    order_id: str
    quantity: int


@dataclass(frozen=True)
class ReleaseFailed:
    sku: str
    order_id: str
    quantity: int
    reserved: int
    reason: str


@dataclass(frozen=True)
class StockReceived:
    sku: str
    quantity: int


@dataclass
class EventLog:
    """A channel-aware log of typed events.

    Each channel is a named logger child under ``base_logger``.
    ``emit(channel, event)`` logs at INFO level with the event's
    dataclass-fields attached as structured ``extra`` data, so
    handlers/formatters can access them.
    """

    base_logger: str = "inventory"
    _records: list[tuple[str, object]] = field(default_factory=list, init=False)

    def emit(self, channel: str, event: object) -> None:
        logger = logging.getLogger(self.base_logger).getChild(channel)
        fields = getattr(event, "__dataclass_fields__", {})
        extra = {name: getattr(event, name) for name in fields}
        logger.info(event.__class__.__name__, extra=extra)
        self._records.append((channel, event))

    def emitted(self, channel: str, event_type: type) -> object | None:
        """Return the first emitted instance of *event_type* on *channel*, or None."""
        for ch, ev in self._records:
            if ch == channel and isinstance(ev, event_type):
                return ev
        return None
