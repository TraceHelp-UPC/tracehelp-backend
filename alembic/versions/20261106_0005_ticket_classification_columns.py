"""Columnas de clasificación automática y sugerida en helpdesk_tickets (US27, T41, T42)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 08:38:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "helpdesk_tickets",
        sa.Column("category", sa.String(length=100), server_default=sa.text("'General'"), nullable=False),
    )
    op.add_column(
        "helpdesk_tickets",
        sa.Column("suggested_category", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "helpdesk_tickets",
        sa.Column(
            "suggested_priority",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="suggested_ticket_priority",
                native_enum=False,
                create_constraint=True,
                length=30,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("helpdesk_tickets", "suggested_priority")
    op.drop_column("helpdesk_tickets", "suggested_category")
    op.drop_column("helpdesk_tickets", "category")
