"""Fragmentos vectorizados de los manuales (kb_knowledge_chunks) con índice HNSW de similitud coseno

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06 02:50:25.266614+00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Neon y la base local ya la tienen; se asegura por si se migra una base nueva
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('kb_knowledge_chunks',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('workspace_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('source_file', sa.String(length=255), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('paragraph_number', sa.Integer(), nullable=False),
    sa.Column('section_title', sa.String(length=200), nullable=True),
    sa.Column('embedding', Vector(768), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['kb_documents.id'], name=op.f('fk_kb_knowledge_chunks_document_id_kb_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['iam_workspaces.id'], name=op.f('fk_kb_knowledge_chunks_workspace_id_iam_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_kb_knowledge_chunks')),
    sa.UniqueConstraint('document_id', 'chunk_index', name='uq_kb_knowledge_chunks_document_id_chunk_index')
    )
    op.create_index('ix_kb_knowledge_chunks_embedding_hnsw', 'kb_knowledge_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_kb_knowledge_chunks_workspace_id', 'kb_knowledge_chunks', ['workspace_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_kb_knowledge_chunks_workspace_id', table_name='kb_knowledge_chunks')
    op.drop_index('ix_kb_knowledge_chunks_embedding_hnsw', table_name='kb_knowledge_chunks')
    op.drop_table('kb_knowledge_chunks')
