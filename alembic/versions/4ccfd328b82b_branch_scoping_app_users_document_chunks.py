"""branch scoping app_users + document_chunks

Revision ID: 4ccfd328b82b
Revises: e3a64a9a0d2c
Create Date: 2026-09-25 11:40:53.845448

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ccfd328b82b'
down_revision: Union[str, Sequence[str], None] = 'e3a64a9a0d2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('app_users', sa.Column('branch_id', sa.String(length=32), nullable=True))
    op.add_column('document_chunks', sa.Column('branch_id', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_document_chunks_branch_id'), 'document_chunks', ['branch_id'], unique=False)
    # La migrazione autogenerate precedente aveva droppato l'indice HNSW
    # (non era dichiarato nei metadati del modello): lo ricostruisco.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_document_chunks_branch_id'), table_name='document_chunks')
    op.drop_column('document_chunks', 'branch_id')
    op.drop_column('app_users', 'branch_id')
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    # ### end Alembic commands ###
