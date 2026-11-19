"""Columnas de escalamiento L2 y reclamo de especialista en helpdesk_tickets (US17, T79)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-19 20:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('helpdesk_tickets', sa.Column('escalated_group', sa.String(length=30), nullable=True))
    op.add_column('helpdesk_tickets', sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        'helpdesk_tickets',
        sa.Column('assigned_specialist_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column('helpdesk_tickets', sa.Column('specialist_claimed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        op.f('ck_helpdesk_tickets_escalated_group'),
        'helpdesk_tickets',
        "escalated_group IS NULL OR escalated_group IN ('REDES','APLICACIONES','INFRAESTRUCTURA','SEGURIDAD')",
    )
    op.create_foreign_key(
        op.f('fk_helpdesk_tickets_assigned_specialist_id'),
        'helpdesk_tickets',
        'iam_users',
        ['assigned_specialist_id'],
        ['id'],
    )
    op.create_index(
        'ix_helpdesk_tickets_assigned_specialist_id',
        'helpdesk_tickets',
        ['assigned_specialist_id'],
        unique=False,
    )
    op.create_index(
        'ix_helpdesk_tickets_workspace_escalated_group',
        'helpdesk_tickets',
        ['workspace_id', 'escalated_group'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_helpdesk_tickets_workspace_escalated_group', table_name='helpdesk_tickets')
    op.drop_index('ix_helpdesk_tickets_assigned_specialist_id', table_name='helpdesk_tickets')
    op.drop_constraint(op.f('fk_helpdesk_tickets_assigned_specialist_id'), 'helpdesk_tickets', type_='foreignkey')
    op.drop_constraint(op.f('ck_helpdesk_tickets_escalated_group'), 'helpdesk_tickets', type_='check')
    op.drop_column('helpdesk_tickets', 'specialist_claimed_at')
    op.drop_column('helpdesk_tickets', 'assigned_specialist_id')
    op.drop_column('helpdesk_tickets', 'escalated_at')
    op.drop_column('helpdesk_tickets', 'escalated_group')
