"""Invitations domain types — stolen from paperchecker, theory-shaped.

Three tables share the organisation-membership world:

  - ``users``       — user_id → (email, default_org)
  - ``members``     — user_id → (org_id, role)   (one org per user here)
  - ``invitations`` — token   → (org_id, invitee_email, role, status,
                                 invited_by, created_at, expires_at)

Timestamps are integer epoch seconds and ``now`` is an operation
argument — the clock is an input, not a hidden effect, so scenarios are
deterministic and the theory stays first-order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from examples.invitations.events import (
    AcceptFailed,
    InvitationAccepted,
    InvitationSent,
    InviteRejected,
)
from specsaver import Args, Result

SEVEN_DAYS = 7 * 24 * 60 * 60


@dataclass
class User:
    user_id: str
    email: str
    default_org: str


@dataclass
class Member:
    user_id: str
    org_id: str
    role: str  # "owner" | "admin" | "member"


@dataclass
class Invitation:
    token: str
    org_id: str
    invitee_email: str
    role: str
    status: str  # "pending" | "accepted" | "revoked"
    invited_by: str
    created_at: int
    expires_at: int


@dataclass(frozen=True)
class InviteArgs(Args):
    token: str
    org_id: str
    inviter_id: str
    invitee_email: str
    role: str
    now: int


@dataclass(frozen=True)
class AcceptArgs(Args):
    token: str
    user_id: str
    now: int


@dataclass(frozen=True)
class InviteReceipt(Result):
    token: str
    org_id: str
    invitee_email: str
    role: str
    expires_at: int


@dataclass(frozen=True)
class AcceptReceipt(Result):
    token: str
    user_id: str
    org_id: str
    role: str


class InvitationError(Exception):
    def __init__(self, token: str, message: str = "") -> None:
        self.token = token
        self.message = message


class NotAuthorizedError(InvitationError):
    code = "NOT_AUTHORIZED"

    def __init__(self, inviter_id: str, org_id: str, message: str = "") -> None:
        super().__init__("", message)
        self.inviter_id = inviter_id
        self.org_id = org_id


class InvitationNotFoundError(InvitationError):
    code = "INVITATION_NOT_FOUND"


class InvitationExpiredError(InvitationError):
    code = "INVITATION_EXPIRED"

    def __init__(self, token: str, expires_at: int, message: str = "") -> None:
        super().__init__(token, message)
        self.expires_at = expires_at


class EmailMismatchError(InvitationError):
    code = "EMAIL_MISMATCH"

    def __init__(self, token: str, invitee_email: str, message: str = "") -> None:
        super().__init__(token, message)
        self.invitee_email = invitee_email


@dataclass(frozen=True)
class InvitationsObserved:
    users: Mapping[str, User]
    members: Mapping[str, Member]
    invitations: Mapping[str, Invitation]
    invite_log: tuple[InvitationSent, ...] = ()
    accept_log: tuple[InvitationAccepted, ...] = ()
    invite_failure_log: tuple[InviteRejected, ...] = ()
    accept_failure_log: tuple[AcceptFailed, ...] = ()


@dataclass(frozen=True)
class InvitationsDerived:
    total_invitations: int = 0
    pending_count: int = 0


@dataclass(frozen=True)
class InvitationsGhost:
    initial_invitation_count: int | None = None


@dataclass(frozen=True)
class InvitationsSpecState:
    observed: InvitationsObserved
    derived: InvitationsDerived
    ghost: InvitationsGhost = field(default_factory=InvitationsGhost)
