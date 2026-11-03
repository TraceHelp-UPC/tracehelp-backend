"""Tablas base de IAM (workspaces, usuarios) y Helpdesk (tickets, evidencias, comentarios)

Revision ID: 0001
Revises: 
Create Date: 2026-11-03 03:12:27.164317+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('iam_workspaces',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('subdomain', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_iam_workspaces')),
    sa.UniqueConstraint('subdomain', name=op.f('uq_iam_workspaces_subdomain'))
    )
    op.create_table('iam_users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('COLLABORATOR', 'ANALYST_L1', 'SPECIALIST_L2', 'IT_LEADER', name='role_name', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('department', sa.String(length=100), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', 'LOCKED', name='user_status', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('availability_status', sa.Enum('AVAILABLE', 'UNAVAILABLE', name='availability_status', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('notify_email', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('notify_inapp', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('external_ad_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id'], ['iam_workspaces.id'], name=op.f('fk_iam_users_workspace_id_iam_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_iam_users')),
    sa.UniqueConstraint('email', name=op.f('uq_iam_users_email'))
    )
    op.create_index('ix_iam_users_workspace_id_role', 'iam_users', ['workspace_id', 'role'], unique=False)
    op.create_table('helpdesk_tickets',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ticket_number', sa.Integer(), sa.Identity(always=False, start=1), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('reporter_id', sa.UUID(), nullable=False),
    sa.Column('assigned_analyst_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('affected_module', sa.String(length=100), nullable=True),
    sa.Column('impact_level', sa.Enum('LOW', 'MEDIUM', 'HIGH', name='impact_level', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'SELF_SERVICE_PROPOSED', 'PENDING_ASSIGNMENT', 'ASSIGNED_L1', 'ESCALATED_L2', 'RESOLVED', 'CLOSED', 'REOPENED', name='ticket_status', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='ticket_priority', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('current_tier', sa.Enum('SELF_SERVICE', 'TIER_L1', 'TIER_L2', name='support_tier', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('external_itsm_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['assigned_analyst_id'], ['iam_users.id'], name=op.f('fk_helpdesk_tickets_assigned_analyst_id_iam_users')),
    sa.ForeignKeyConstraint(['reporter_id'], ['iam_users.id'], name=op.f('fk_helpdesk_tickets_reporter_id_iam_users')),
    sa.ForeignKeyConstraint(['workspace_id'], ['iam_workspaces.id'], name=op.f('fk_helpdesk_tickets_workspace_id_iam_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_helpdesk_tickets')),
    sa.UniqueConstraint('ticket_number', name=op.f('uq_helpdesk_tickets_ticket_number'))
    )
    op.create_index('ix_helpdesk_tickets_assigned_analyst_id', 'helpdesk_tickets', ['assigned_analyst_id'], unique=False)
    op.create_index('ix_helpdesk_tickets_created_at', 'helpdesk_tickets', ['created_at'], unique=False)
    op.create_index('ix_helpdesk_tickets_reporter_id', 'helpdesk_tickets', ['reporter_id'], unique=False)
    op.create_index('ix_helpdesk_tickets_workspace_id_status', 'helpdesk_tickets', ['workspace_id', 'status'], unique=False)
    op.create_table('helpdesk_ticket_comments',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ticket_id', sa.UUID(), nullable=False),
    sa.Column('author_id', sa.UUID(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('is_ai_generated', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_internal_note', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['iam_users.id'], name=op.f('fk_helpdesk_ticket_comments_author_id_iam_users')),
    sa.ForeignKeyConstraint(['ticket_id'], ['helpdesk_tickets.id'], name=op.f('fk_helpdesk_ticket_comments_ticket_id_helpdesk_tickets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_helpdesk_ticket_comments'))
    )
    op.create_index('ix_helpdesk_ticket_comments_ticket_id', 'helpdesk_ticket_comments', ['ticket_id'], unique=False)
    op.create_table('helpdesk_ticket_evidences',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('ticket_id', sa.UUID(), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=50), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('file_data', sa.LargeBinary(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['ticket_id'], ['helpdesk_tickets.id'], name=op.f('fk_helpdesk_ticket_evidences_ticket_id_helpdesk_tickets'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_helpdesk_ticket_evidences'))
    )
    op.create_index('ix_helpdesk_ticket_evidences_ticket_id', 'helpdesk_ticket_evidences', ['ticket_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_helpdesk_ticket_evidences_ticket_id', table_name='helpdesk_ticket_evidences')
    op.drop_table('helpdesk_ticket_evidences')
    op.drop_index('ix_helpdesk_ticket_comments_ticket_id', table_name='helpdesk_ticket_comments')
    op.drop_table('helpdesk_ticket_comments')
    op.drop_index('ix_helpdesk_tickets_workspace_id_status', table_name='helpdesk_tickets')
    op.drop_index('ix_helpdesk_tickets_reporter_id', table_name='helpdesk_tickets')
    op.drop_index('ix_helpdesk_tickets_created_at', table_name='helpdesk_tickets')
    op.drop_index('ix_helpdesk_tickets_assigned_analyst_id', table_name='helpdesk_tickets')
    op.drop_table('helpdesk_tickets')
    op.drop_index('ix_iam_users_workspace_id_role', table_name='iam_users')
    op.drop_table('iam_users')
    op.drop_table('iam_workspaces')
