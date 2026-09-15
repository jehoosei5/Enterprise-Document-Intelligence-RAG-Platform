from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.db.models import DocumentStatus, SourceFormat


class DocumentOut(BaseModel):
    id: str
    filename: str
    title: str
    category: str | None
    is_public: bool
    source_format: SourceFormat
    size_bytes: int
    page_count: int | None
    ocr_used: bool
    chunk_count: int | None
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(DocumentOut):
    pass


class DuplicateConflictDocument(BaseModel):
    """Minimal existing-doc info returned in upload 409s so the UI can prompt."""

    id: str
    filename: str
    title: str
    source_format: SourceFormat

    model_config = {"from_attributes": True}


class DuplicateConflictDetail(BaseModel):
    """Structured body for POST /documents 409 Conflict responses.

    - duplicate_exact: same stem + same type — blocked; client must rename.
    - duplicate_name_different_type: same stem, different type — client may
      retry with confirm_different_type=true (accept) or rename_to=... .
    """

    code: Literal["duplicate_exact", "duplicate_name_different_type"]
    message: str
    incoming_filename: str
    incoming_format: SourceFormat
    existing_documents: list[DuplicateConflictDocument]
    actions: list[Literal["accept", "rename"]]


class ShareRequest(BaseModel):
    email: EmailStr


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    is_public: bool | None = None


class DocumentContentUpdateRequest(BaseModel):
    content: str
