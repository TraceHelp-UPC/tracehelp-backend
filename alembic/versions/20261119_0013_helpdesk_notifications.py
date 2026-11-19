"""Tabla helpdesk_notifications para notificaciones de estado y mensajes (US19, T91)

Revision ID: 0013
Revises: 0010
Create Date: 2026-11-19 18:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "helpdesk_notifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "type IN ('TICKET_STATUS_CHANGED','MESSAGE_POSTED','ESCALATED_TICKET_RESOLVED')",
            name=op.f("ck_helpdesk_notifications_type"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["iam_workspaces.id"],
            name=op.f("fk_helpdesk_notifications_workspace_id_iam_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["iam_users.id"],
            name=op.f("fk_helpdesk_notifications_recipient_id_iam_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["helpdesk_tickets.id"],
            name=op.f("fk_helpdesk_notifications_ticket_id_helpdesk_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_helpdesk_notifications")),
    )
    op.create_index(
        "ix_helpdesk_notifications_recipient_created",
        "helpdesk_notifications",
        ["recipient_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_helpdesk_notifications_recipient_unread",
        "helpdesk_notifications",
        ["recipient_id"],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_helpdesk_notifications_recipient_unread", table_name="helpdesk_notifications")
    op.drop_index("ix_helpdesk_notifications_recipient_created", table_name="helpdesk_notifications")
    op.drop_table("helpdesk_notifications")
