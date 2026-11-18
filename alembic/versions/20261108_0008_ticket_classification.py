"""Clasificación técnica del incidente en triaje y ticket (US27, T41, T42)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-08 12:25:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = "'Red/VPN', 'Correo', 'Accesos', 'Hardware', 'Software', 'Otro'"
PRIORITIES = "'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"


def upgrade() -> None:
    op.add_column('helpdesk_tickets', sa.Column('category', sa.String(length=30), nullable=True))
    op.create_check_constraint(
        op.f('ck_helpdesk_tickets_ticket_category'),
        'helpdesk_tickets',
        f"category IN ({CATEGORIES})",
    )
    op.add_column('triage_diagnoses', sa.Column('suggested_category', sa.String(length=30), nullable=True))
    op.add_column('triage_diagnoses', sa.Column('suggested_priority', sa.String(length=30), nullable=True))
    op.create_check_constraint(
        op.f('ck_triage_diagnoses_suggested_category'),
        'triage_diagnoses',
        f"suggested_category IN ({CATEGORIES})",
    )
    op.create_check_constraint(
        op.f('ck_triage_diagnoses_suggested_priority'),
        'triage_diagnoses',
        f"suggested_priority IN ({PRIORITIES})",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_triage_diagnoses_suggested_priority'), 'triage_diagnoses', type_='check')
    op.drop_constraint(op.f('ck_triage_diagnoses_suggested_category'), 'triage_diagnoses', type_='check')
    op.drop_column('triage_diagnoses', 'suggested_priority')
    op.drop_column('triage_diagnoses', 'suggested_category')
    op.drop_constraint(op.f('ck_helpdesk_tickets_ticket_category'), 'helpdesk_tickets', type_='check')
    op.drop_column('helpdesk_tickets', 'category')
