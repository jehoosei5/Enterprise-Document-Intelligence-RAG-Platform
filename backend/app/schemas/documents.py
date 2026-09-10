from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.models import DocumentStatus, SourceFormat


class DocumentOut(BaseModel):
    id: str
    filename: str
    title: str
    category: str | None
    is_public: bool
    source_format: SourceFormat
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


class ShareRequest(BaseModel):
    email: EmailStr
