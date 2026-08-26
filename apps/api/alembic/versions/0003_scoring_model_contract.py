"""scoring_model carries what the contract requires of it

The table could not serve `ScoringModel` from `docs/openapi.yaml`. Three fields the contract
lists as **required** had no column: `name_az` and `name_en` (`ScoringModelSummary.required`)
and `groups` (`ScoringModel.required`); `status` was declared and also had no column. The
phase-1E seed worked around it by storing `name_az` in a single `name` column and stuffing
the rest into the free-form `notes` JSONB, and flagged the gap rather than filing a migration
itself — correctly, since migrations are the orchestrator's.

Left out on purpose. `currency` is fixed at AZN by ADR-007 with no conversion anywhere in the
code, and a column whose only legal value is AZN invites the illusion that another one would
work; it is served as the constant it is. `total_max` is the sum of the criteria maxima —
stored separately it can drift from them, and then two numbers both claim to be the total.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS = postgresql.ENUM(
    "draft", "proposed", "active", "retired", name="scoring_model_status", create_type=False
)


def upgrade() -> None:
    STATUS.create(op.get_bind(), checkfirst=True)

    # `name` becomes the AZ name — that is what the seed put there — and the EN name is
    # backfilled from it so the NOT NULL can be added without inventing a translation. The
    # seed rewrites both from the JSON on its next run.
    op.alter_column("scoring_model", "name", new_column_name="name_az")
    op.add_column("scoring_model", sa.Column("name_en", sa.String(length=255), nullable=True))
    op.execute("UPDATE scoring_model SET name_en = name_az WHERE name_en IS NULL")
    op.alter_column("scoring_model", "name_en", nullable=False)

    op.add_column(
        "scoring_model",
        sa.Column("status", STATUS, nullable=False, server_default="active"),
    )
    op.add_column(
        "scoring_model",
        sa.Column(
            "groups",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("scoring_model", "status", server_default=None)
    op.alter_column("scoring_model", "groups", server_default=None)


def downgrade() -> None:
    op.drop_column("scoring_model", "groups")
    op.drop_column("scoring_model", "status")
    op.drop_column("scoring_model", "name_en")
    op.alter_column("scoring_model", "name_az", new_column_name="name")
    STATUS.drop(op.get_bind(), checkfirst=True)
