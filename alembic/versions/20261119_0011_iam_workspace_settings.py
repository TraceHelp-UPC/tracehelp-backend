"""Tabla iam_workspace_settings para configuración por workspace (US07, T62)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 18:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'iam_workspace_settings',
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('similarity_threshold', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('self_service_threshold', sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column('retrieval_top_k', sa.SmallInteger(), nullable=True),
        sa.Column('strict_grounding', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            'similarity_threshold IS NULL OR similarity_threshold BETWEEN 0.50 AND 0.95',
            name=op.f('ck_iam_workspace_settings_similarity_threshold_range'),
        ),
        sa.CheckConstraint(
            'self_service_threshold IS NULL OR self_service_threshold <= 0.99',
            name=op.f('ck_iam_workspace_settings_self_service_threshold_max'),
        ),
        sa.CheckConstraint(
            'self_service_threshold IS NULL OR similarity_threshold IS NULL '
            'OR self_service_threshold >= similarity_threshold',
            name=op.f('ck_iam_workspace_settings_self_service_ge_similarity'),
        ),
        sa.CheckConstraint(
            'retrieval_top_k IS NULL OR retrieval_top_k BETWEEN 1 AND 10',
            name=op.f('ck_iam_workspace_settings_retrieval_top_k_range'),
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'],
            ['iam_workspaces.id'],
            name=op.f('fk_iam_workspace_settings_workspace_id_iam_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['updated_by'],
            ['iam_users.id'],
            name=op.f('fk_iam_workspace_settings_updated_by_iam_users'),
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('workspace_id', name=op.f('pk_iam_workspace_settings')),
    )


def downgrade() -> None:
    op.drop_table('iam_workspace_settings')
