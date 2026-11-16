"""Record model usage

Revision ID: 20261116_model_usage
Revises: 20261116_documents
Create Date: 2026-11-16 08:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261116_model_usage"
down_revision = "20261116_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=True),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("cost_is_estimated", sa.Boolean(), nullable=False),
        sa.Column("pricing_version", sa.String(length=50), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_usage_profile_id", "model_usage", ["profile_id"], unique=False)
    op.create_index("ix_model_usage_created_at", "model_usage", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_model_usage_created_at", table_name="model_usage")
    op.drop_index("ix_model_usage_profile_id", table_name="model_usage")
    op.drop_table("model_usage")
