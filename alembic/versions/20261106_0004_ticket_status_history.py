"""Tabla de historial de cambios de estado del ticket (US14, T45)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 08:20:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = (
    "OPEN",
    "SELF_SERVICE_PROPOSED",
    "PENDING_ASSIGNMENT",
    "ASSIGNED_L1",
    "ESCALATED_L2",
    "RESOLVED",
    "CLOSED",
    "REOPENED",
)


def upgrade() -> None:
    op.create_table(
        "helpdesk_ticket_status_history",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("ticket_id", sa.UUID(), nullable=False),
        sa.Column("changed_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "previous_status",
            sa.Enum(
                *_STATUS_VALUES,
                name="previous_ticket_status",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "new_status",
            sa.Enum(
                *_STATUS_VALUES,
                name="new_ticket_status",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["iam_users.id"],
            name=op.f("fk_helpdesk_ticket_status_history_changed_by_id_iam_users"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["helpdesk_tickets.id"],
            name=op.f("fk_helpdesk_ticket_status_history_ticket_id_helpdesk_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_helpdesk_ticket_status_history")),
    )
    op.create_index(
        "ix_helpdesk_status_history_ticket_id",
        "helpdesk_ticket_status_history",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_helpdesk_status_history_changed_at",
        "helpdesk_ticket_status_history",
        ["changed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_helpdesk_status_history_changed_at", table_name="helpdesk_ticket_status_history")
    op.drop_index("ix_helpdesk_status_history_ticket_id", table_name="helpdesk_ticket_status_history")
    op.drop_table("helpdesk_ticket_status_history")
