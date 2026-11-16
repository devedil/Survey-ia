"""Persist minimal Chrome extension actions

Revision ID: 20261116_chrome_extension_audit
Revises: 20261116_browser_audit
Create Date: 2026-11-16 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20261116_chrome_extension_audit"
down_revision = "20261116_browser_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chrome_extension_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("origin", sa.String(length=512), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("control_type", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chrome_extension_audit_events_profile_id",
        "chrome_extension_audit_events",
        ["profile_id"],
    )
    op.create_index(
        "ix_chrome_extension_audit_events_created_at",
        "chrome_extension_audit_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chrome_extension_audit_events_created_at", table_name="chrome_extension_audit_events")
    op.drop_index("ix_chrome_extension_audit_events_profile_id", table_name="chrome_extension_audit_events")
    op.drop_table("chrome_extension_audit_events")
