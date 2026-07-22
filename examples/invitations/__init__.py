"""Invitations example — stolen from paperchecker, built on SQLAlchemy."""

from examples.invitations.contract import accept_contract, invite_contract
from examples.invitations.projection import (
    InvitationsExecutionContext,
    InvitationsScenarioRunner,
    InvitationsScenarioWitness,
    _AcceptService,
    _InviteService,
    build_accept_witness,
    build_invite_witness,
    cleanup,
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

invite_runner = InvitationsScenarioRunner(
    invite_contract, _InviteService(), build_invite_witness,
)
accept_runner = InvitationsScenarioRunner(
    accept_contract, _AcceptService(), build_accept_witness,
)


def _verify_invite(row, pre_only=False):
    return invite_runner.check_pre(row) if pre_only else invite_runner.run(row)


def _verify_accept(row, pre_only=False):
    return accept_runner.check_pre(row) if pre_only else accept_runner.run(row)


__verify_runner__ = {
    "invite.feature": _verify_invite,
    "accept.feature": _verify_accept,
}

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
    "InvitationsExecutionContext",
    "InvitationsGhost",
    "InvitationsObserved",
    "InvitationsScenarioRunner",
    "InvitationsScenarioWitness",
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
    "cleanup",
    "invite_contract",
    "invite_runner",
]
