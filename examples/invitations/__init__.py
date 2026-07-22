"""Invitations example — stolen from paperchecker, built on SQLAlchemy."""

from examples.invitations.contract import accept_contract, invite_contract
from examples.invitations.domain import invitations_domain as _domain
from examples.invitations.projection import (
    build_accept_witness,
    build_invite_witness,
)
from examples.invitations.service import InvitationService
from examples.invitations.types import (
    AcceptArgs,
    AcceptReceipt,
    EmailMismatchError,
    Invitation,
    InvitationError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationsDerived,
    InvitationsGhost,
    InvitationsObserved,
    InvitationsSpecState,
    InviteArgs,
    InviteReceipt,
    Member,
    NotAuthorizedError,
    User,
)

FEATURE = "invite.feature"

_runners = _domain.runners()
invite_runner = _runners["invite.feature"]
accept_runner = _runners["accept.feature"]

__verify_runner__ = _domain.verify_runner()

__all__ = [
    "FEATURE",
    "AcceptArgs",
    "AcceptReceipt",
    "EmailMismatchError",
    "Invitation",
    "InvitationError",
    "InvitationExpiredError",
    "InvitationNotFoundError",
    "InvitationService",
    "InvitationsDerived",
    "InvitationsGhost",
    "InvitationsObserved",
    "InvitationsSpecState",
    "InviteArgs",
    "InviteReceipt",
    "Member",
    "NotAuthorizedError",
    "User",
    "accept_contract",
    "accept_runner",
    "build_accept_witness",
    "build_invite_witness",

    "invite_contract",
    "invite_runner",
]
