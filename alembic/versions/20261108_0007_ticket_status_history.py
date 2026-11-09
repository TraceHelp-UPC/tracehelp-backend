"""Historial de cambios de estado del ticket (helpdesk_ticket_status_history)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08 12:15:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = (
    "'OPEN', 'SELF_SERVICE_PROPOSED', 'PENDING_ASSIGNMENT', "
    "'ASSIGNED_L1', 'ESCALATED_L2', 'RESOLVED', 'CLOSED', 'REOPENED'"
)


def upgrade() -> None:
    op.create_table(
        'helpdesk_ticket_status_history',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('previous_status', sa.String(length=30), nullable=False),
        sa.Column('new_status', sa.String(length=30), nullable=False),
        sa.Column('changed_by', sa.UUID(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            f"previous_status IN ({STATUSES})",
            name=op.f('ck_helpdesk_ticket_status_history_previous_status'),
        ),
        sa.CheckConstraint(
            f"new_status IN ({STATUSES})",
            name=op.f('ck_helpdesk_ticket_status_history_new_status'),
        ),
        sa.ForeignKeyConstraint(
            ['changed_by'],
            ['iam_users.id'],
            name=op.f('fk_helpdesk_ticket_status_history_changed_by_iam_users'),
        ),
        sa.ForeignKeyConstraint(
            ['ticket_id'],
            ['helpdesk_tickets.id'],
            name=op.f('fk_helpdesk_ticket_status_history_ticket_id_helpdesk_tickets'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_helpdesk_ticket_status_history')),
    )
    op.create_index(
        'ix_helpdesk_ticket_status_history_ticket_changed',
        'helpdesk_ticket_status_history',
        ['ticket_id', 'changed_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_helpdesk_ticket_status_history_ticket_changed', table_name='helpdesk_ticket_status_history')
    op.drop_table('helpdesk_ticket_status_history')
