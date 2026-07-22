"""Core telemetry event types — shared by all domains.

``EventLog`` is an append-only record of typed events indexed by
channel (e.g. "email", "reservation", "accept").  It is symmetric
with the contract language's view of event logs as immutable tuples
of typed dataclass instances.

``FaultState`` is an opt-in fault-injection handle shared between
the scenario runner and service wrappers.  Domains that don't need
simulated faults can ignore it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass
class EventLog:
    """A channel-aware log of typed events.

    Each channel is a named logger child under ``base_logger``.
    ``emit(channel, event)`` logs at INFO level with the event's
    dataclass-fields attached as structured ``extra`` data, so
    handlers/formatters can access them.

    ``_records`` carries the full ordered history; the projection
    partitions it by channel and event type when building the
    abstract SpecState.
    """

    base_logger: str = "specsaver"
    _records: list[tuple[str, object]] = field(default_factory=list, init=False)

    def emit(self, channel: str, event: object) -> None:
        logger = logging.getLogger(self.base_logger).getChild(channel)
        fields = getattr(event, "__dataclass_fields__", {})
        extra = {name: getattr(event, name) for name in fields}
        logger.info(event.__class__.__name__, extra=extra)
        self._records.append((channel, event))

    def emitted(self, channel: str, event_type: type) -> object | None:
        """Return the first emitted instance of *event_type* on *channel*,
        or None."""
        for ch, ev in self._records:
            if ch == channel and isinstance(ev, event_type):
                return ev
        return None


@dataclass
class FaultState:
    """Mutable slot for fault injection between runner and wrapper.

    Usage pattern::

        _fault = FaultState()
        _fault.inject("simulated_fault")
        # ... runner calls wrapper.execute(context, args) ...
        # wrapper checks _fault.consume() and raises SimulatedFaultError
    """

    pending: str | None = None

    def inject(self, fault_name: str) -> None:
        self.pending = fault_name

    def consume(self) -> str | None:
        f = self.pending
        self.pending = None
        return f
