"""Diagnósticos del triaje automático (triage_diagnoses)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07 16:30:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTCOMES = "'ANSWERED', 'INSUFFICIENT_EVIDENCE', 'MODEL_DECLINED', 'INVALID_RESPONSE', 'PROVIDER_ERROR'"
LEVELS = "'SELF_SERVICE', 'GROUNDED', 'LOW_CONFIDENCE'"
REVIEWS = "'PENDING_REVIEW', 'SELF_SERVICE_PROPOSED', 'NOT_APPLICABLE'"


def upgrade() -> None:
    op.create_table('triage_diagnoses',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('ticket_id', sa.UUID(), nullable=False),
    sa.Column('outcome', sa.String(length=30), nullable=False),
    sa.Column('confidence_level', sa.String(length=30), nullable=True),
    sa.Column('best_score', sa.Float(), nullable=True),
    sa.Column('similarity_threshold', sa.Float(), nullable=True),
    sa.Column('self_service_threshold', sa.Float(), nullable=True),
    sa.Column('review_status', sa.String(length=30), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('outcome_reason', sa.Text(), nullable=True),
    sa.Column('ocr_legible', sa.Boolean(), nullable=True),
    sa.Column('ocr_error_codes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('ocr_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(f"outcome IN ({OUTCOMES})", name=op.f('ck_triage_diagnoses_diagnosis_outcome')),
    sa.CheckConstraint(f"confidence_level IN ({LEVELS})", name=op.f('ck_triage_diagnoses_confidence_level')),
    sa.CheckConstraint(f"review_status IN ({REVIEWS})", name=op.f('ck_triage_diagnoses_review_status')),
    sa.ForeignKeyConstraint(['ticket_id'], ['helpdesk_tickets.id'], name=op.f('fk_triage_diagnoses_ticket_id_helpdesk_tickets'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['iam_workspaces.id'], name=op.f('fk_triage_diagnoses_workspace_id_iam_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_triage_diagnoses')),
    sa.UniqueConstraint('ticket_id', name=op.f('uq_triage_diagnoses_ticket_id'))
    )
    op.create_index(op.f('ix_triage_diagnoses_workspace_id'), 'triage_diagnoses', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_triage_diagnoses_review_status'), 'triage_diagnoses', ['review_status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_triage_diagnoses_review_status'), table_name='triage_diagnoses')
    op.drop_index(op.f('ix_triage_diagnoses_workspace_id'), table_name='triage_diagnoses')
    op.drop_table('triage_diagnoses')
