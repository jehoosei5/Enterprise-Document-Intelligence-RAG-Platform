"""SQLAlchemy models. Chunk content and citation metadata live in Qdrant's
payload, not here — MySQL only tracks document/user/permission/eval-log
metadata.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    # Nullable: a Google-only account has no password. hashed_password/google_sub
    # are independent capability flags, not a single provider enum — an account
    # can have either or both (see app/api/auth.py's Google sign-in linking logic).
    hashed_password: Mapped[str | None] = mapped_column(String(60), nullable=True)  # bcrypt hash, fixed 60 chars
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)

    # Forgot-password: one active reset at a time (overwritten on each new
    # request), token itself never stored raw — only its hash.
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # user-editable, defaults to filename
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    # No team/org model exists in this system — just two real states: a
    # private draft, or visible to everyone at the company.
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)
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


class Conversation(Base):
    """Every query belongs to one of these, even a standalone one-off
    question (a conversation of length 1) — simpler than special-casing
    "no conversation" throughout the query pipeline and history endpoints.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)  # first question, truncated
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class QueryLog(Base):
    """One row per /query call — the per-query debug trace and the data
    behind the aggregate eval dashboard. Chunk-level detail (dense/sparse/
    fused/reranked candidates, cited sources) is stored as JSON rather than
    normalized tables — it's write-once, read-as-a-blob debug data, not
    something queried relationally.
    """

    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Set when this query was asked via a document's "Ask about this
    # document" panel — powers that document's "Recent Questions Asked".
    # Not a FK: the document may since have been deleted, and this is a
    # read-only historical trace like the rest of this table.
    scoped_document_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Retrieval debug trace: lists of {chunk_id, doc_id, filename, locator, score}-shaped dicts.
    retrieved_dense: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retrieved_sparse: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fused_candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reranked_chunks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)

    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Eval scores — nullable: null when evaluate=false, or when a metric
    # failed open, or when there was no retrieved context to evaluate.
    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_precision_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    answer_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    eval_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    feedback: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "up" | "down"

    latency_retrieval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_rerank_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_llm_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_eval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_total_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
