"""Bitácora de auditoría inmutable (analytics_audit_log)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-08 12:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'analytics_audit_log',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('ticket_id', sa.UUID(), nullable=True),
        sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('integrity_hash', sa.String(length=64), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['iam_users.id'], name=op.f('fk_analytics_audit_log_actor_id_iam_users')),
        sa.ForeignKeyConstraint(
            ['ticket_id'],
            ['helpdesk_tickets.id'],
            name=op.f('fk_analytics_audit_log_ticket_id_helpdesk_tickets'),
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'],
            ['iam_workspaces.id'],
            name=op.f('fk_analytics_audit_log_workspace_id_iam_workspaces'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analytics_audit_log')),
    )
    op.create_index(
        'ix_analytics_audit_log_workspace_occurred',
        'analytics_audit_log',
        ['workspace_id', 'occurred_at'],
        unique=False,
    )
    op.create_index('ix_analytics_audit_log_event_type', 'analytics_audit_log', ['event_type'], unique=False)
    op.create_index('ix_analytics_audit_log_ticket_id', 'analytics_audit_log', ['ticket_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_analytics_audit_log_ticket_id', table_name='analytics_audit_log')
    op.drop_index('ix_analytics_audit_log_event_type', table_name='analytics_audit_log')
    op.drop_index('ix_analytics_audit_log_workspace_occurred', table_name='analytics_audit_log')
    op.drop_table('analytics_audit_log')
