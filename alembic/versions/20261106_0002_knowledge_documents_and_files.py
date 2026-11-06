"""Tablas de Knowledge Management: documentos técnicos (kb_documents) y archivos originales (kb_document_files)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06 02:36:54.103579+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('kb_document_files',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kb_document_files'))
    )
    op.create_table('kb_documents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('uploaded_by', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('file_name', sa.String(length=255), nullable=False),
    sa.Column('document_format', sa.Enum('PDF', 'MARKDOWN', name='document_format', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('file_size_bytes', sa.Integer(), nullable=False),
    sa.Column('storage_uri', sa.String(length=500), nullable=False),
    sa.Column('ingestion_status', sa.Enum('PENDING', 'PROCESSING', 'VECTORIZED', 'FAILED', name='ingestion_status', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('chunk_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vectorized_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['uploaded_by'], ['iam_users.id'], name=op.f('fk_kb_documents_uploaded_by_iam_users')),
    sa.ForeignKeyConstraint(['workspace_id'], ['iam_workspaces.id'], name=op.f('fk_kb_documents_workspace_id_iam_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kb_documents')),
    sa.UniqueConstraint('job_id', name=op.f('uq_kb_documents_job_id'))
    )
    op.create_index('ix_kb_documents_created_at', 'kb_documents', ['created_at'], unique=False)
    op.create_index('ix_kb_documents_workspace_id_status', 'kb_documents', ['workspace_id', 'ingestion_status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_kb_documents_workspace_id_status', table_name='kb_documents')
    op.drop_index('ix_kb_documents_created_at', table_name='kb_documents')
    op.drop_table('kb_documents')
    op.drop_table('kb_document_files')
