"""evaluation table replaces application.second_rubric

The optional second evaluator (spec §10.3) was a JSONB column beside the first evaluator's
rubric. That shape cannot say *who* scored, cannot hold a third opinion and cannot be
queried. It becomes a table: one row per evaluator per application, ``is_primary`` marking
the set the decision is taken from.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_id", sa.Uuid(), nullable=True),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["application.id"],
            name=op.f("fk_evaluation_application_id_application"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluator_id"],
            ["app_user.id"],
            name=op.f("fk_evaluation_evaluator_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation")),
        sa.UniqueConstraint(
            "application_id", "evaluator_id", name=op.f("uq_evaluation_application_id_evaluator_id")
        ),
    )
    op.create_index(
        op.f("ix_evaluation_application_id"), "evaluation", ["application_id"], unique=False
    )
    op.create_index(
        op.f("ix_evaluation_evaluator_id"), "evaluation", ["evaluator_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_application_primary",
        "evaluation",
        ["application_id", "is_primary"],
        unique=False,
    )

    # Carry any existing second-evaluator rubric over as a non-primary row before the
    # column goes. Phase 0 shipped no data, but a re-run against a seeded database must
    # not lose an officer's work.
    op.execute(
        sa.text(
            """
            INSERT INTO evaluation (id, application_id, evaluator_id, rubric, computed,
                                    is_primary, created_at)
            SELECT gen_random_uuid(), id, NULL, second_rubric, NULL, false, now()
            FROM application
            WHERE second_rubric IS NOT NULL
            """
        )
    )
    op.drop_column("application", "second_rubric")


def downgrade() -> None:
    op.add_column(
        "application",
        sa.Column("second_rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE application a
            SET second_rubric = e.rubric
            FROM evaluation e
            WHERE e.application_id = a.id AND e.is_primary = false
            """
        )
    )
    op.drop_index("ix_evaluation_application_primary", table_name="evaluation")
    op.drop_index(op.f("ix_evaluation_evaluator_id"), table_name="evaluation")
    op.drop_index(op.f("ix_evaluation_application_id"), table_name="evaluation")
    op.drop_table("evaluation")
