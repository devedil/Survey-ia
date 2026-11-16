"""Persist browser action audit events

Revision ID: 20261116_browser_audit
Revises: 20261116_controlled_memory
Create Date: 2026-11-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261116_browser_audit"
down_revision = "20261116_controlled_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_browser_audit_events_session_id", "browser_audit_events", ["session_id"])
    op.create_index("ix_browser_audit_events_profile_id", "browser_audit_events", ["profile_id"])
    op.create_index("ix_browser_audit_events_created_at", "browser_audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_browser_audit_events_created_at", table_name="browser_audit_events")
    op.drop_index("ix_browser_audit_events_profile_id", table_name="browser_audit_events")
    op.drop_index("ix_browser_audit_events_session_id", table_name="browser_audit_events")
    op.drop_table("browser_audit_events")
