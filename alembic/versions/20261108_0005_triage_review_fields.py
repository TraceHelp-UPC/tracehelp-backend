"""Campos de la revisión humana (HITL) en triage_diagnoses

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08 10:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REVIEWS = "'PENDING_REVIEW', 'SELF_SERVICE_PROPOSED', 'NOT_APPLICABLE'"
NEW_REVIEWS = (
    "'PENDING_REVIEW', 'SELF_SERVICE_PROPOSED', 'NOT_APPLICABLE', "
    "'APPROVED', 'EDITED_AND_APPROVED', 'REJECTED', 'MANUAL_RESPONSE'"
)


def upgrade() -> None:
    op.add_column('triage_diagnoses', sa.Column('reviewed_by', sa.UUID(), nullable=True))
    op.add_column('triage_diagnoses', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('triage_diagnoses', sa.Column('final_summary', sa.Text(), nullable=True))
    op.add_column(
        'triage_diagnoses',
        sa.Column('final_steps', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column('triage_diagnoses', sa.Column('manual_response', sa.Text(), nullable=True))
    op.add_column('triage_diagnoses', sa.Column('review_note', sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f('fk_triage_diagnoses_reviewed_by_iam_users'), 'triage_diagnoses', 'iam_users', ['reviewed_by'], ['id']
    )
    op.drop_constraint(op.f('ck_triage_diagnoses_review_status'), 'triage_diagnoses', type_='check')
    op.create_check_constraint(
        op.f('ck_triage_diagnoses_review_status'), 'triage_diagnoses', f"review_status IN ({NEW_REVIEWS})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_triage_diagnoses_review_status'), 'triage_diagnoses', type_='check')
    op.execute(
        "UPDATE triage_diagnoses SET review_status = 'NOT_APPLICABLE' "
        "WHERE review_status IN ('APPROVED', 'EDITED_AND_APPROVED', 'REJECTED', 'MANUAL_RESPONSE')"
    )
    op.create_check_constraint(
        op.f('ck_triage_diagnoses_review_status'), 'triage_diagnoses', f"review_status IN ({OLD_REVIEWS})"
    )
    op.drop_constraint(op.f('fk_triage_diagnoses_reviewed_by_iam_users'), 'triage_diagnoses', type_='foreignkey')
    op.drop_column('triage_diagnoses', 'review_note')
    op.drop_column('triage_diagnoses', 'manual_response')
    op.drop_column('triage_diagnoses', 'final_steps')
    op.drop_column('triage_diagnoses', 'final_summary')
    op.drop_column('triage_diagnoses', 'reviewed_at')
    op.drop_column('triage_diagnoses', 'reviewed_by')
