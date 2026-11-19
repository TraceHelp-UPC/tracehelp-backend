"""Tabla de jobs periódicos del scheduler (TS09, T60)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-18 12:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'shared_scheduler_jobs',
        sa.Column('job_name', sa.String(length=80), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=20), nullable=True),
        sa.Column('last_error', sa.String(length=200), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('interval_seconds > 0', name=op.f('ck_shared_scheduler_jobs_interval_positive')),
        sa.PrimaryKeyConstraint('job_name', name=op.f('pk_shared_scheduler_jobs')),
    )


def downgrade() -> None:
    op.drop_table('shared_scheduler_jobs')
