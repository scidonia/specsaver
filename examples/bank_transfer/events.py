"""Event channels — structured output side effects.

Channels are backed by Python's standard :mod:`logging` facility so that
emissions can be captured, mocked, or redirected with standard tools
(``caplog``, ``unittest.mock``, ``logging.config``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TransferCompleted:
    transaction_id: str
    source_id: str
    target_id: str
    amount: int


@dataclass(frozen=True)
class FundsReceived:
    target_id: str
    amount: int


@dataclass
class EventLog:
    """A channel-aware log of typed events.

    Each channel is a named logger child under ``base_logger``.
    ``emit(channel, event)`` logs at INFO level with the event's
    dataclass-fields attached as structured ``extra`` data, so
    handlers/formatters can access them.

        caplog = pytest.logging.LogCaptureFixture(...)
        with caplog.at_level(logging.INFO, logger="specsaver.audit"):
            log.emit("audit", TransferCompleted("tx-1", "A", "B", 100))
        assert "TransferCompleted" in caplog.text
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
        """Return the first emitted instance of *event_type* on *channel*, or None."""
        for ch, ev in self._records:
            if ch == channel and isinstance(ev, event_type):
                return ev
        return None
