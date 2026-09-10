"""add title, category, is_public to documents

Revision ID: fa3cad496904
Revises: ce51def058f9
Create Date: 2026-09-10 15:29:19.427975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa3cad496904'
down_revision: Union[str, None] = 'ce51def058f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # title added nullable first so existing rows (if any) don't break the
    # ADD COLUMN — backfilled from filename, then tightened to NOT NULL.
    op.add_column('documents', sa.Column('title', sa.String(length=255), nullable=True))
    op.add_column('documents', sa.Column('category', sa.String(length=100), nullable=True))
    op.add_column('documents', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f('ix_documents_category'), 'documents', ['category'], unique=False)

    documents = sa.table('documents', sa.column('title', sa.String), sa.column('filename', sa.String))
    op.execute(documents.update().where(documents.c.title.is_(None)).values(title=documents.c.filename))

    op.alter_column('documents', 'title', existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_category'), table_name='documents')
    op.drop_column('documents', 'is_public')
    op.drop_column('documents', 'category')
    op.drop_column('documents', 'title')
