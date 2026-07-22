"""Invitations — SqlDomain declaration (replaces most of projection.py)."""

from examples.invitations.contract import accept_contract, invite_contract
from examples.invitations.events import (
    AcceptFailed,
    InvitationAccepted,
    InvitationSent,
    InviteRejected,
)
from examples.invitations.projection import (
    _AcceptService,
    _InviteService,
    build_accept_witness,
    build_invite_witness,
)
from examples.invitations.types import (
    Invitation,
    InvitationsDerived,
    InvitationsGhost,
    InvitationsObserved,
    InvitationsSpecState,
    Member,
    User,
)
from specsaver.domain import (
    SqlDomain,
    SqlMaterializer,
    SqlOperation,
    SqlProjection,
    TableSpec,
)

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    default_org TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    user_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations (
    token TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    invitee_email TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    invited_by TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
"""

_TABLES = (
    TableSpec(
        name="users", key="user_id",
        columns=("user_id", "email", "default_org"),
        witness_key="users",
    ),
    TableSpec(
        name="members", key="user_id",
        columns=("user_id", "org_id", "role"),
        witness_key="members",
    ),
    TableSpec(
        name="invitations", key="token",
        columns=("token", "org_id", "invitee_email", "role",
                 "status", "invited_by", "created_at", "expires_at"),
        witness_key="invitations",
    ),
)


def _extract_observed(context, table_dicts):
    users = {
        k: User(
            user_id=k, email=v["email"],
            default_org=v["default_org"],
        )
        for k, v in table_dicts["users"].items()
    }
    members = {
        k: Member(
            user_id=k, org_id=v["org_id"], role=v["role"],
        )
        for k, v in table_dicts["members"].items()
    }
    invitations = {
        k: Invitation(
            token=k, org_id=v["org_id"],
            invitee_email=v["invitee_email"], role=v["role"],
            status=v["status"], invited_by=v["invited_by"],
            created_at=v["created_at"], expires_at=v["expires_at"],
        )
        for k, v in table_dicts["invitations"].items()
    }
    records = context.events._records
    return InvitationsObserved(
        users=users,
        members=members,
        invitations=invitations,
        invite_log=tuple(
            e for _, e in records if isinstance(e, InvitationSent)
        ),
        accept_log=tuple(
            e for _, e in records if isinstance(e, InvitationAccepted)
        ),
        invite_failure_log=tuple(
            e for _, e in records if isinstance(e, InviteRejected)
        ),
        accept_failure_log=tuple(
            e for _, e in records if isinstance(e, AcceptFailed)
        ),
    )


def _compute_derived(observed):
    return InvitationsDerived(
        total_invitations=len(observed.invitations),
        pending_count=sum(
            1 for i in observed.invitations.values()
            if i.status == "pending"
        ),
    )


invitations_domain = SqlDomain(
    name="invitations",
    package="examples.invitations",
    materializer=SqlMaterializer(
        ddl=_DDL,
        tables=_TABLES,
        ghost_init=lambda w: InvitationsGhost(
            initial_invitation_count=len(w.invitations)
        ),
        tempfile_prefix="specsaver_inv_",
    ),
    projection=SqlProjection(
        state_type=InvitationsSpecState,
        observed_type=InvitationsObserved,
        derived_type=InvitationsDerived,
        ghost_type=InvitationsGhost,
        tables=_TABLES,
        extract_observed=_extract_observed,
        compute_derived=_compute_derived,
    ),
    operations=(
        SqlOperation(
            invite_contract, _InviteService(),
            build_invite_witness, "invite.feature",
        ),
        SqlOperation(
            accept_contract, _AcceptService(),
            build_accept_witness, "accept.feature",
        ),
    ),
)
