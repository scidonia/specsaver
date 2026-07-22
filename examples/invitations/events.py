"""Telemetry channels for the invitations domain.

  - ``InvitationSent``     — the Brevo email event: one per successful
                             invite, carrying the accept-link token.
  - ``InvitationAccepted`` — domain event: an invite was accepted.
  - ``InviteRejected``     — counter: a non-owner/admin tried to invite.
  - ``AcceptFailed``       — counter: an accept was refused (expired,
                             email mismatch, unknown token).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InvitationSent:
    token: str
    org_id: str
    invitee_email: str
    role: str
    expires_at: int


@dataclass(frozen=True)
class InvitationAccepted:
    token: str
    user_id: str
    org_id: str
    role: str


@dataclass(frozen=True)
class InviteRejected:
    inviter_id: str
    org_id: str
    invitee_email: str
    reason: str


@dataclass(frozen=True)
class AcceptFailed:
    token: str
    user_id: str
    reason: str


@dataclass
class EventLog:
    """A channel-aware log of typed events (see inventory.events)."""

    base_logger: str = "invitations"
    _records: list[tuple[str, object]] = field(default_factory=list, init=False)

    def emit(self, channel: str, event: object) -> None:
        logger = logging.getLogger(self.base_logger).getChild(channel)
        fields = getattr(event, "__dataclass_fields__", {})
        extra = {name: getattr(event, name) for name in fields}
        logger.info(event.__class__.__name__, extra=extra)
        self._records.append((channel, event))

    def emitted(self, channel: str, event_type: type) -> object | None:
        for ch, ev in self._records:
            if ch == channel and isinstance(ev, event_type):
                return ev
        return None
