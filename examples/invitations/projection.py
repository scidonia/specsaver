"""Projection and refinement bridge for the invitations domain.

Symmetric architecture (see inventory.projection):
  - materialize(witness) → ExecutionContext  (write abstract → concrete)
  - snapshot(context) → SpecState            (read concrete → abstract)

Exports ``InvitationsScenarioRunner`` — the single entry point bundling
all domain-specific wiring for both the CLI and pytest.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, create_engine, text

from examples.invitations.events import (
    AcceptFailed,
    EventLog,
    InvitationAccepted,
    InvitationSent,
    InviteRejected,
)
from examples.invitations.types import (
    AcceptArgs,
    EmailMismatchError,
    Invitation,
    InvitationExpiredError,
    InvitationsDerived,
    InvitationsGhost,
    InvitationsObserved,
    InvitationsSpecState,
    InviteArgs,
    Member,
    NotAuthorizedError,
    User,
)
from specsaver.scenario_runner import ScenarioRunner

# ---------------------------------------------------------------------------
# ExecutionContext / ScenarioWitness
# ---------------------------------------------------------------------------


@dataclass
class InvitationsExecutionContext:
    """The concrete world the implementation operates on."""

    engine: Engine
    events: EventLog = field(default_factory=EventLog)
    ghost: InvitationsGhost = field(default_factory=InvitationsGhost)


@dataclass(frozen=True)
class InvitationsScenarioWitness:
    """Produced from a Gherkin Examples row by a build_*_witness function."""

    users: dict[str, User]
    members: dict[str, Member]
    invitations: dict[str, Invitation]
    args: InviteArgs | AcceptArgs
    ghost: InvitationsGhost = field(default_factory=InvitationsGhost)


# ---------------------------------------------------------------------------
# Database schema helpers
# ---------------------------------------------------------------------------


_SCHEMA = """
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


def _populate(
    conn: sqlite3.Connection,
    users: dict[str, User],
    members: dict[str, Member],
    invitations: dict[str, Invitation],
) -> None:
    for table in ("users", "members", "invitations"):
        conn.execute(f"DELETE FROM {table}")
    for u in users.values():
        conn.execute(
            "INSERT INTO users (user_id, email, default_org) VALUES (?, ?, ?)",
            (u.user_id, u.email, u.default_org),
        )
    for m in members.values():
        conn.execute(
            "INSERT INTO members (user_id, org_id, role) VALUES (?, ?, ?)",
            (m.user_id, m.org_id, m.role),
        )
    for i in invitations.values():
        conn.execute(
            "INSERT INTO invitations"
            " (token, org_id, invitee_email, role, status,"
            "  invited_by, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (i.token, i.org_id, i.invitee_email, i.role, i.status,
             i.invited_by, i.created_at, i.expires_at),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Materializer / Projection
# ---------------------------------------------------------------------------


class InvitationsMaterializer:
    """Creates a concrete ExecutionContext (temp SQLite DB) from a witness."""

    def materialize(
        self, witness: InvitationsScenarioWitness
    ) -> InvitationsExecutionContext:
        fd, path = tempfile.mkstemp(suffix=".db", prefix="specsaver_inv_")
        os.close(fd)
        with sqlite3.connect(path) as conn:
            conn.executescript(_SCHEMA)
            _populate(conn, witness.users, witness.members,
                      witness.invitations)
        return InvitationsExecutionContext(
            engine=create_engine(f"sqlite:///{path}"),
            events=EventLog(),
            ghost=witness.ghost,
        )


class InvitationsProjection:
    """Projects the execution context into an immutable SpecState.

    Used symmetrically: before execution (pre-state) and after execution
    (post-state).
    """

    def snapshot(
        self, context: InvitationsExecutionContext
    ) -> InvitationsSpecState:
        with context.engine.connect() as conn:
            user_rows = conn.execute(
                text("SELECT user_id, email, default_org FROM users")
            ).fetchall()
            member_rows = conn.execute(
                text("SELECT user_id, org_id, role FROM members")
            ).fetchall()
            inv_rows = conn.execute(
                text(
                    "SELECT token, org_id, invitee_email, role, status,"
                    " invited_by, created_at, expires_at FROM invitations"
                )
            ).fetchall()

        users = {
            r[0]: User(user_id=r[0], email=r[1], default_org=r[2])
            for r in user_rows
        }
        members = {
            r[0]: Member(user_id=r[0], org_id=r[1], role=r[2])
            for r in member_rows
        }
        invitations = {
            r[0]: Invitation(
                token=r[0], org_id=r[1], invitee_email=r[2], role=r[3],
                status=r[4], invited_by=r[5], created_at=r[6],
                expires_at=r[7],
            )
            for r in inv_rows
        }

        records = context.events._records
        observed = InvitationsObserved(
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
        derived = InvitationsDerived(
            total_invitations=len(invitations),
            pending_count=sum(
                1 for i in invitations.values() if i.status == "pending"
            ),
        )
        ghost = InvitationsGhost(
            initial_invitation_count=context.ghost.initial_invitation_count
        )
        return InvitationsSpecState(
            observed=observed, derived=derived, ghost=ghost
        )


# ---------------------------------------------------------------------------
# Witness builders — Gherkin Examples row → ScenarioWitness
# ---------------------------------------------------------------------------
# Row columns (invite.feature):
#   token org inviter inviter_role invitee_email role now outcome
# Row columns (accept.feature):
#   token org invitee_email role user user_email sent_days_ago now outcome


def _split(row: dict[str, str], key: str) -> list[str]:
    raw = row.get(key, "").strip()
    return [p for p in raw.split(";") if p] if raw else []


def build_invite_witness(row: dict[str, str]) -> InvitationsScenarioWitness:
    members: dict[str, Member] = {}
    if row.get("inviter_role") and row["inviter_role"] != "none":
        members[row["inviter"]] = Member(
            user_id=row["inviter"],
            org_id=row["org"],
            role=row["inviter_role"],
        )
    return InvitationsScenarioWitness(
        users={},
        members=members,
        invitations={},
        args=InviteArgs(
            token=row["token"],
            org_id=row["org"],
            inviter_id=row["inviter"],
            invitee_email=row["invitee_email"],
            role=row["role"],
            now=int(row["now"]),
        ),
    )


def build_accept_witness(row: dict[str, str]) -> InvitationsScenarioWitness:
    now = int(row["now"])
    sent_days_ago = int(row["sent_days_ago"])
    created = now - sent_days_ago * 24 * 60 * 60
    from examples.invitations.types import SEVEN_DAYS

    invitations = {
        row["token"]: Invitation(
            token=row["token"],
            org_id=row["org"],
            invitee_email=row["invitee_email"],
            role=row["role"],
            status="pending",
            invited_by="owner",
            created_at=created,
            expires_at=created + SEVEN_DAYS,
        )
    }
    users = {
        row["user"]: User(
            user_id=row["user"],
            email=row["user_email"],
            default_org="",
        )
    }
    return InvitationsScenarioWitness(
        users=users,
        members={},
        invitations=invitations,
        args=AcceptArgs(
            token=row["token"], user_id=row["user"], now=now
        ),
    )


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


def cleanup(context: InvitationsExecutionContext) -> None:
    """Dispose the engine and remove the temp database after a test."""
    path = context.engine.url.database
    context.engine.dispose()
    if path and os.path.exists(path):
        os.unlink(path)


# ---------------------------------------------------------------------------
# Effect-emitting impl wrappers
# ---------------------------------------------------------------------------


class _InviteService:
    """Invite under contract: service + InvitationSent / InviteRejected."""

    def __init__(self, inner: Any = None) -> None:
        from examples.invitations.service import InvitationService

        self._inner = inner or InvitationService()

    def execute(self, context, args):
        try:
            result = self._inner.invite(
                context.engine, args.token, args.org_id, args.inviter_id,
                args.invitee_email, args.role, args.now,
            )
        except NotAuthorizedError as exc:
            context.events.emit(
                "invite_failure",
                InviteRejected(
                    inviter_id=args.inviter_id,
                    org_id=args.org_id,
                    invitee_email=args.invitee_email,
                    reason=exc.code,
                ),
            )
            raise

        context.events.emit(
            "email",
            InvitationSent(
                token=result.token,
                org_id=result.org_id,
                invitee_email=result.invitee_email,
                role=result.role,
                expires_at=result.expires_at,
            ),
        )
        return result


class _AcceptService:
    """Accept under contract: service + InvitationAccepted / AcceptFailed."""

    def __init__(self, inner: Any = None) -> None:
        from examples.invitations.service import InvitationService

        self._inner = inner or InvitationService()

    def execute(self, context, args):
        try:
            result = self._inner.accept(
                context.engine, args.token, args.user_id, args.now
            )
        except (InvitationExpiredError, EmailMismatchError) as exc:
            context.events.emit(
                "accept_failure",
                AcceptFailed(
                    token=args.token,
                    user_id=args.user_id,
                    reason=exc.code,
                ),
            )
            raise

        context.events.emit(
            "accept",
            InvitationAccepted(
                token=result.token,
                user_id=result.user_id,
                org_id=result.org_id,
                role=result.role,
            ),
        )
        return result


class InvitationsScenarioRunner(ScenarioRunner):
    """Bundles the invitations wiring for ONE operation (see inventory)."""

    def __init__(self, contract, impl, witness_builder) -> None:
        super().__init__(
            contract,
            materializer=InvitationsMaterializer(),
            projection=InvitationsProjection(),
            impl=impl,
            witness_builder=witness_builder,
            cleanup=cleanup,
        )
