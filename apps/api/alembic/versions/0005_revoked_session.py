"""revoked sessions, so that logging out actually ends the session

The session cookie is a stateless HMAC signature carrying `sub`, `role` and `exp`, and
`POST /auth/logout` only cleared cookies. A cookie captured before logout therefore kept
authenticating for the remainder of its eight hours — on a shared machine, exactly the
window logging out is meant to close. `User.is_active` was the only revocation mechanism,
and deactivating an account is not what a user asks for when they click "Log out"
(3B, finding 3).

The design keeps the property that made the session stateless in the first place: nothing is
read from the database to *establish* a session, only to find out whether a particular one
has been withdrawn — a single indexed primary-key lookup on a table that holds one row per
logout and only until that token would have expired anyway. A horizontally-scaled deployment
still needs no shared session store, because rows here are self-expiring rather than
authoritative.

Per-token (`jti`), not per-user: signing out of a phone must not sign out the desktop.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_session",
        # The token's own id, from the `jti` claim. Primary key: checking a session is one
        # index lookup, and revoking the same token twice is idempotent by construction.
        sa.Column("jti", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # When the token would have expired anyway. After this instant the row proves
        # nothing the signature does not already, so it can be deleted.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("revoked_session")
