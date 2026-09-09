"""SQLAlchemy models. Chunk content and citation metadata live in Qdrant's
payload, not here — MySQL only tracks document/user/permission metadata.
Eval logs (v4a) get their own tables when that version lands.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(60), nullable=False)  # bcrypt hash, fixed 60 chars
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class SourceFormat(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN = "markdown"
    TEXT = "text"
    CSV = "csv"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_format: Mapped[SourceFormat] = mapped_column(Enum(SourceFormat), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_used: Mapped[bool] = mapped_column(default=False, nullable=False)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), nullable=False, default=DocumentStatus.PROCESSING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DocumentShare(Base):
    """Presence of a row = the user has read access to the document. Owner
    access is implied by Document.owner_id and doesn't need a row here.
    """

    __tablename__ = "document_shares"
    __table_args__ = (UniqueConstraint("document_id", "user_id", name="uq_document_share"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
