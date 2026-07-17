"""Event channels — structured output side effects."""

from __future__ import annotations

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

    Each channel is a named sink (e.g. "audit", "notification", "stdout").
    Events are appended in order.  The contract specifies which *types* of
    event should appear on which channels.
    """

    channels: dict[str, list[object]] = field(default_factory=dict)

    def emit(self, channel: str, event: object) -> None:
        self.channels.setdefault(channel, []).append(event)

    def emitted(self, channel: str, event_type: type) -> bool:
        return any(isinstance(e, event_type) for e in self.channels.get(channel, []))

    def snapshot(self) -> dict[str, list[object]]:
        return {ch: list(evs) for ch, evs in self.channels.items()}
