"""Invitation service — SQLAlchemy implementation.

Semantics stolen from paperchecker's ``create_invitation`` /
``accept_invitation``, reshaped for the theory:

  - the token is supplied by the caller (accept links embed it), so the
    insert key is args-resolved — no hidden randomness;
  - ``now`` is an argument (epoch seconds), so expiry is deterministic;
  - the accept path requires the invitee not already be a member —
    re-accepts are rejected at the contract boundary.

Transactions use ``engine.begin()``: commit on success, rollback on any
raised domain error.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from examples.invitations.types import (
    SEVEN_DAYS,
    AcceptReceipt,
    EmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InviteReceipt,
    NotAuthorizedError,
)

_SELECT_MEMBER = text(
    "SELECT org_id, role FROM members WHERE user_id = :user_id"
)
_SELECT_INVITATION = text(
    "SELECT org_id, invitee_email, role, status, expires_at"
    " FROM invitations WHERE token = :token"
)
_SELECT_USER = text(
    "SELECT email, default_org FROM users WHERE user_id = :user_id"
)


class InvitationService:
    """Implementation — contracts are attached externally."""

    def invite(
        self,
        engine: Engine,
        token: str,
        org_id: str,
        inviter_id: str,
        invitee_email: str,
        role: str,
        now: int,
    ) -> InviteReceipt:
        with engine.begin() as conn:
            inviter = conn.execute(
                _SELECT_MEMBER, {"user_id": inviter_id}
            ).fetchone()
            if inviter is None or inviter[1] not in ("owner", "admin"):
                raise NotAuthorizedError(
                    inviter_id, org_id,
                    f"{inviter_id!r} may not invite to {org_id!r}",
                )

            expires_at = now + SEVEN_DAYS
            conn.execute(
                text(
                    "INSERT INTO invitations"
                    " (token, org_id, invitee_email, role, status,"
                    "  invited_by, created_at, expires_at)"
                    " VALUES (:token, :org_id, :email, :role, 'pending',"
                    "         :inviter, :now, :expires)"
                ),
                {
                    "token": token,
                    "org_id": org_id,
                    "email": invitee_email,
                    "role": role,
                    "inviter": inviter_id,
                    "now": now,
                    "expires": expires_at,
                },
            )

        return InviteReceipt(
            token=token,
            org_id=org_id,
            invitee_email=invitee_email,
            role=role,
            expires_at=expires_at,
        )

    def accept(
        self,
        engine: Engine,
        token: str,
        user_id: str,
        now: int,
    ) -> AcceptReceipt:
        with engine.begin() as conn:
            inv = conn.execute(
                _SELECT_INVITATION, {"token": token}
            ).fetchone()
            if inv is None or inv[3] != "pending":
                raise InvitationNotFoundError(
                    token, f"No pending invitation for token {token!r}"
                )

            org_id, invitee_email, role, _status, expires_at = inv

            if now > expires_at:
                raise InvitationExpiredError(
                    token, expires_at,
                    f"Invitation expired at {expires_at}",
                )

            user = conn.execute(
                _SELECT_USER, {"user_id": user_id}
            ).fetchone()
            if user is None:
                raise EmailMismatchError(
                    token, invitee_email,
                    f"Unknown user {user_id!r}",
                )
            if user[0] != invitee_email:
                raise EmailMismatchError(
                    token, invitee_email,
                    f"Invitation was sent to {invitee_email!r}",
                )

            existing = conn.execute(
                _SELECT_MEMBER, {"user_id": user_id}
            ).fetchone()
            if existing is None:
                conn.execute(
                    text(
                        "INSERT INTO members (user_id, org_id, role)"
                        " VALUES (:user_id, :org_id, :role)"
                    ),
                    {"user_id": user_id, "org_id": org_id, "role": role},
                )

            conn.execute(
                text("UPDATE invitations SET status = 'accepted'"
                     " WHERE token = :token"),
                {"token": token},
            )
            conn.execute(
                text("UPDATE users SET default_org = :org_id"
                     " WHERE user_id = :user_id"),
                {"org_id": org_id, "user_id": user_id},
            )

        return AcceptReceipt(
            token=token, user_id=user_id, org_id=org_id, role=role
        )
