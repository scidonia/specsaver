"""Invitations — contracts for invite and accept.

The interesting verification surface, beyond the inventory example:

  - **row insertion** (invite inserts a pending invitation keyed by the
    args-resolved token; accept inserts a members row keyed by user_id)
    — checked by the semantic frame, no postcondition needed for the
    bare fact of insertion;
  - **multi-table deltas** (accept touches invitations, members, users);
  - **time as an argument** — expiry is a pure comparison on ``args.now``
    against a stored epoch, so it is contract-checkable and translatable.

Stolen from paperchecker's invitations.feature.
"""

from examples.invitations.service import InvitationService
from examples.invitations.types import (
    SEVEN_DAYS,
    AcceptArgs,
    EmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationsGhost,
    InviteArgs,
    NotAuthorizedError,
)
from specsaver.contract_model import Contract, ExcExit, StateField
from specsaver.logic import extends_by_one

# ---------------------------------------------------------------------------
# Shared domain properties
# ---------------------------------------------------------------------------


def _invariant_invitations_legal(state) -> bool:
    return all(
        i.status in ("pending", "accepted", "revoked")
        and i.expires_at == i.created_at + SEVEN_DAYS
        for i in state.observed.invitations.values()
    )


_DERIVES = {
    "total_invitations": lambda state: len(state.observed.invitations),
    "pending_count": lambda state: sum(
        1 for i in state.observed.invitations.values()
        if i.status == "pending"
    ),
}

_STATE_SCHEMA = {
    "users": StateField(
        type_hint="Mapping[str, User]", provenance="observed",
    ),
    "members": StateField(
        type_hint="Mapping[str, Member]", provenance="observed",
    ),
    "invitations": StateField(
        type_hint="Mapping[str, Invitation]", provenance="observed",
    ),
    "invite_log": StateField(
        type_hint="tuple[InvitationSent, ...]", provenance="observed",
    ),
    "accept_log": StateField(
        type_hint="tuple[InvitationAccepted, ...]", provenance="observed",
    ),
    "invite_failure_log": StateField(
        type_hint="tuple[InviteRejected, ...]", provenance="observed",
    ),
    "accept_failure_log": StateField(
        type_hint="tuple[AcceptFailed, ...]", provenance="observed",
    ),
    "total_invitations": StateField(type_hint="int", provenance="derived"),
    "pending_count": StateField(type_hint="int", provenance="derived"),
    "initial_invitation_count": StateField(
        type_hint="int", provenance="ghost",
    ),
}


def _ghost_init(witness) -> InvitationsGhost:
    return InvitationsGhost(
        initial_invitation_count=len(witness["invitations"])
    )


_GHOST_TRANSITIONS = [
    lambda old_g, args, result, new_g: (
        old_g.initial_invitation_count == new_g.initial_invitation_count
    ),
]

_GHOST_INVARIANTS = [
    lambda state: state.ghost.initial_invitation_count is not None,
]


# ---------------------------------------------------------------------------
# invite
# ---------------------------------------------------------------------------


invite_contract = Contract(
    InvitationService.invite,
    args_type=InviteArgs,
    feature="invite.feature",
    when='"<inviter>" invites "<invitee_email>" to "<org>" as "<role>"',
    requires=[
        # Admissibility must hold for ALL outcomes, including the
        # NotAuthorizedError exit — so authorization itself lives in the
        # exception's ``when``, not here.
        lambda state, args: args.token not in state.observed.invitations,
    ],
    ensures=[
        # --- the inserted row, exact fields -----------------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].status == "pending"
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].org_id == args.org_id
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].invitee_email
            == args.invitee_email
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].role == args.role
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].invited_by
            == args.inviter_id
        ),
        # --- 7-day expiry, pinned to the time argument ------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].created_at == args.now
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].expires_at
            == args.now + SEVEN_DAYS
        ),
        # --- receipt agrees ---------------------------------------------
        lambda old_s, args, result, new_s: (
            result.token == args.token
            and result.expires_at == args.now + SEVEN_DAYS
        ),
        # --- the Brevo email event, exact fields ------------------------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.invite_log, new_s.observed.invite_log,
            lambda e: (
                e.token == args.token
                and e.org_id == args.org_id
                and e.invitee_email == args.invitee_email
                and e.role == args.role
                and e.expires_at == args.now + SEVEN_DAYS
            ),
        ),
    ],
    exceptions=[
        ExcExit(
            raises=NotAuthorizedError,
            when=[
                lambda state, args: (
                    args.inviter_id not in state.observed.members
                    or state.observed.members[args.inviter_id].org_id
                    != args.org_id
                    or state.observed.members[args.inviter_id].role
                    not in ("owner", "admin")
                ),
            ],
            writes={"state.invite_failure_log"},
            ensures=[
                lambda state, args, exc, after_s: extends_by_one(
                    state.observed.invite_failure_log,
                    after_s.observed.invite_failure_log,
                    lambda f: (
                        f.inviter_id == args.inviter_id
                        and f.org_id == args.org_id
                        and f.invitee_email == args.invitee_email
                        and f.reason == NotAuthorizedError.code
                    ),
                ),
            ],
        ),
    ],
    invariants=[_invariant_invitations_legal],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=InvitationsGhost,
    ghost_init=_ghost_init,
    ghost_transitions=_GHOST_TRANSITIONS,
    ghost_invariants=_GHOST_INVARIANTS,
    writes={
        "state.invitations[token]",
        "state.invite_log",
    },
    reads={
        "state.members[inviter_id].org_id",
        "state.members[inviter_id].role",
    },
)


# ---------------------------------------------------------------------------
# accept
# ---------------------------------------------------------------------------


def _pending(state, args) -> bool:
    inv = state.observed.invitations.get(args.token)
    return inv is not None and inv.status == "pending"


accept_contract = Contract(
    InvitationService.accept,
    args_type=AcceptArgs,
    feature="accept.feature",
    when='"<user>" accepts invitation "<token>"',
    requires=[
        # Holds for the success, EmailMismatch, and Expired rows alike:
        # every scenario starts from a pending invitation.  The exits
        # discriminate on expiry and email below.
        lambda state, args: _pending(state, args),
    ],
    ensures=[
        # --- invitation marked accepted ----------------------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.invitations[args.token].status == "accepted"
        ),
        # --- membership row inserted with the invitation's org/role -----
        lambda old_s, args, result, new_s: (
            new_s.observed.members[args.user_id].org_id
            == old_s.observed.invitations[args.token].org_id
        ),
        lambda old_s, args, result, new_s: (
            new_s.observed.members[args.user_id].role
            == old_s.observed.invitations[args.token].role
        ),
        # --- invited org becomes the user's active org -------------------
        lambda old_s, args, result, new_s: (
            new_s.observed.users[args.user_id].default_org
            == old_s.observed.invitations[args.token].org_id
        ),
        # --- receipt agrees ----------------------------------------------
        lambda old_s, args, result, new_s: (
            result.org_id == old_s.observed.invitations[args.token].org_id
            and result.user_id == args.user_id
        ),
        # --- domain event, exact fields ----------------------------------
        lambda old_s, args, result, new_s: extends_by_one(
            old_s.observed.accept_log, new_s.observed.accept_log,
            lambda e: (
                e.token == args.token
                and e.user_id == args.user_id
                and e.org_id == old_s.observed.invitations[args.token].org_id
                and e.role == old_s.observed.invitations[args.token].role
            ),
        ),
    ],
    exceptions=[
        ExcExit(
            raises=InvitationNotFoundError,
            when=[
                lambda state, args: not _pending(state, args),
            ],
        ),
        ExcExit(
            raises=InvitationExpiredError,
            when=[
                lambda state, args: _pending(state, args),
                lambda state, args: (
                    args.now
                    > state.observed.invitations[args.token].expires_at
                ),
            ],
            writes={"state.accept_failure_log"},
            ensures=[
                lambda state, args, exc, after_s: extends_by_one(
                    state.observed.accept_failure_log,
                    after_s.observed.accept_failure_log,
                    lambda f: (
                        f.token == args.token
                        and f.user_id == args.user_id
                        and f.reason == InvitationExpiredError.code
                    ),
                ),
            ],
        ),
        ExcExit(
            raises=EmailMismatchError,
            when=[
                lambda state, args: _pending(state, args),
                lambda state, args: (
                    args.now
                    <= state.observed.invitations[args.token].expires_at
                ),
                lambda state, args: (
                    args.user_id not in state.observed.users
                    or state.observed.users[args.user_id].email
                    != state.observed.invitations[args.token].invitee_email
                ),
            ],
            writes={"state.accept_failure_log"},
            ensures=[
                lambda state, args, exc, after_s: extends_by_one(
                    state.observed.accept_failure_log,
                    after_s.observed.accept_failure_log,
                    lambda f: (
                        f.token == args.token
                        and f.user_id == args.user_id
                        and f.reason == EmailMismatchError.code
                    ),
                ),
                # --- the error message names the invited address --------
                lambda state, args, exc, after_s: (
                    exc.invitee_email
                    == state.observed.invitations[args.token].invitee_email
                ),
            ],
        ),
    ],
    invariants=[_invariant_invitations_legal],
    derives=_DERIVES,
    state_schema=_STATE_SCHEMA,
    ghost_state=InvitationsGhost,
    ghost_init=_ghost_init,
    ghost_transitions=_GHOST_TRANSITIONS,
    ghost_invariants=_GHOST_INVARIANTS,
    writes={
        "state.invitations[token].status",
        "state.members[user_id]",
        "state.users[user_id].default_org",
        "state.accept_log",
    },
    reads={
        "state.invitations[token].status",
        "state.invitations[token].expires_at",
        "state.invitations[token].org_id",
        "state.invitations[token].role",
        "state.invitations[token].invitee_email",
        "state.users[user_id].email",
    },
)
