"""Persist reviewed proposals and provenance-aware memory

Revision ID: 20261116_controlled_memory
Revises: 20261116_model_usage
Create Date: 2026-11-16 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261116_controlled_memory"
down_revision = "20261116_model_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_facts",
        sa.Column("source_type", sa.String(length=50), server_default="user", nullable=False),
    )
    op.add_column("profile_facts", sa.Column("source_id", sa.String(length=36), nullable=True))
    op.add_column(
        "profile_facts",
        sa.Column("category", sa.String(length=100), server_default="general", nullable=False),
    )
    op.add_column(
        "profile_facts",
        sa.Column("status", sa.String(length=30), server_default="verified", nullable=False),
    )
    op.add_column(
        "profile_facts",
        sa.Column("sensitivity", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "profile_facts",
        sa.Column("consent_to_retrieve", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("profile_facts", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("profile_facts", sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE profile_facts SET status = CASE WHEN is_verified THEN 'verified' ELSE 'pending' END"
    )
    op.execute(
        "UPDATE profile_facts SET confirmed_at = created_at WHERE is_verified = TRUE"
    )
    op.create_index("ix_profile_facts_status", "profile_facts", ["status"], unique=False)

    op.create_table(
        "profile_fact_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fact_id", sa.String(length=36), nullable=False),
        sa.Column("change_type", sa.String(length=40), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["fact_id"], ["profile_facts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_fact_revisions_fact_id", "profile_fact_revisions", ["fact_id"])

    op.create_table(
        "answer_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("support_status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("answer_format", sa.String(length=30), nullable=False),
        sa.Column("question_analysis", sa.JSON(), nullable=False),
        sa.Column("needs_user_input", sa.Boolean(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_proposals_profile_id", "answer_proposals", ["profile_id"])
    op.create_index("ix_answer_proposals_status", "answer_proposals", ["status"])
    op.create_index("ix_answer_proposals_created_at", "answer_proposals", ["created_at"])

    op.create_table(
        "answer_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["answer_proposals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_answer_sources_proposal_id", "answer_sources", ["proposal_id"])

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("feedback_type", sa.String(length=30), nullable=False),
        sa.Column("correction", sa.Text(), nullable=True),
        sa.Column("previous_answer", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("approved_for_memory", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["answer_proposals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_feedback_proposal_id", "user_feedback", ["proposal_id"])
    op.create_index("ix_user_feedback_created_at", "user_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_feedback_created_at", table_name="user_feedback")
    op.drop_index("ix_user_feedback_proposal_id", table_name="user_feedback")
    op.drop_table("user_feedback")
    op.drop_index("ix_answer_sources_proposal_id", table_name="answer_sources")
    op.drop_table("answer_sources")
    op.drop_index("ix_answer_proposals_created_at", table_name="answer_proposals")
    op.drop_index("ix_answer_proposals_status", table_name="answer_proposals")
    op.drop_index("ix_answer_proposals_profile_id", table_name="answer_proposals")
    op.drop_table("answer_proposals")
    op.drop_index("ix_profile_fact_revisions_fact_id", table_name="profile_fact_revisions")
    op.drop_table("profile_fact_revisions")
    op.drop_index("ix_profile_facts_status", table_name="profile_facts")
    op.drop_column("profile_facts", "valid_until")
    op.drop_column("profile_facts", "confirmed_at")
    op.drop_column("profile_facts", "consent_to_retrieve")
    op.drop_column("profile_facts", "sensitivity")
    op.drop_column("profile_facts", "status")
    op.drop_column("profile_facts", "category")
    op.drop_column("profile_facts", "source_id")
    op.drop_column("profile_facts", "source_type")
