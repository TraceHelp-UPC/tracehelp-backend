"""Grupo del especialista L2 en iam_users (US09, T69)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19 12:00:00.000000+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('iam_users', sa.Column('specialist_group', sa.String(length=30), nullable=True))
    op.create_check_constraint(
        op.f('ck_iam_users_specialist_group'),
        'iam_users',
        "specialist_group IS NULL OR specialist_group IN ('REDES','APLICACIONES','INFRAESTRUCTURA','SEGURIDAD')",
    )
    op.create_check_constraint(
        op.f('ck_iam_users_specialist_group_role'),
        'iam_users',
        "specialist_group IS NULL OR role = 'SPECIALIST_L2'",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_iam_users_specialist_group_role'), 'iam_users', type_='check')
    op.drop_constraint(op.f('ck_iam_users_specialist_group'), 'iam_users', type_='check')
    op.drop_column('iam_users', 'specialist_group')
