"""create interview sessions and turns

Revision ID: a7e3b5d91c42
Revises: c4f1a9b2e7d3
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7e3b5d91c42"
down_revision: str | None = "c4f1a9b2e7d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("jd_analysis", JSONB, nullable=False),
        sa.Column("plan", JSONB, nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("trace_id", sa.String(36), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sessions_user_created",
        "interview_sessions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(200), nullable=True),
        sa.Column("evaluation", JSONB, nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_turns_session", "interview_turns", ["session_id", "turn_index"])
    op.create_index("ix_interview_turns_topic", "interview_turns", ["topic"])


def downgrade() -> None:
    op.drop_table("interview_turns")
    op.drop_table("interview_sessions")
