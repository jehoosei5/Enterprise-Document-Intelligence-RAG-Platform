"""add size_bytes to documents

Revision ID: 7f564b0fb2b8
Revises: 52ce5e7bd576
Create Date: 2026-09-11 23:32:01.356837

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f564b0fb2b8'
down_revision: Union[str, None] = '52ce5e7bd576'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default='0' so the NOT NULL add succeeds against existing rows;
    # the backfill below then replaces it with each row's real file size
    # where the uploaded file still exists on disk.
    op.add_column('documents', sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'))

    from app.core.config import get_settings

    upload_path = get_settings().upload_path
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, filename FROM documents")).fetchall()
    for doc_id, filename in rows:
        ext = Path(filename).suffix.lower()
        file_path = upload_path / f"{doc_id}{ext}"
        if file_path.exists():
            conn.execute(
                sa.text("UPDATE documents SET size_bytes = :size WHERE id = :id"),
                {"size": file_path.stat().st_size, "id": doc_id},
            )


def downgrade() -> None:
    op.drop_column('documents', 'size_bytes')
