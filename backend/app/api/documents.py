import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.chunking.chunker import chunk_document
from app.core import storage
from app.core.config import Settings, get_settings
from app.db.models import Document, DocumentShare, DocumentStatus, QueryLog, SourceFormat, User
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_texts
from app.embeddings.sparse_embeddings import embed_texts as sparse_embed_texts
from app.ingestion.dispatch import SUPPORTED_EXTENSIONS, UnsupportedFileTypeError, parse_document
from app.retrieval.qdrant_store import delete_document as delete_document_vectors
from app.retrieval.qdrant_store import upsert_chunks
from app.schemas.documents import (
    DocumentContentUpdateRequest,
    DocumentOut,
    DocumentUpdateRequest,
    DocumentUploadResponse,
    ShareRequest,
)
from app.schemas.queries import QueryLogSummary

router = APIRouter(prefix="/documents", tags=["documents"])

# Formats whose "content" is just text we already fetch/render as such —
# the only ones content-editing supports (see PUT .../content below).
_TEXT_BACKED_FORMATS = {SourceFormat.TEXT, SourceFormat.MARKDOWN, SourceFormat.CSV}


def _ingest_and_index(document: Document, dest_path: Path, settings: Settings) -> None:
    """Parse -> chunk -> embed -> index the file at dest_path, updating
    document's status/page_count/chunk_count in place. Shared by upload
    and content-replace so both stay in sync with one implementation.
    Caller is responsible for db.commit()/refresh() afterward.
    """
    try:
        ingested = parse_document(str(dest_path), doc_id=document.id, filename=document.filename)
        chunks = chunk_document(
            ingested,
            target_tokens=settings.chunk_target_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        texts = [c.text for c in chunks]
        dense_vectors = embed_texts(texts)
        sparse_vectors = sparse_embed_texts(texts)
        upsert_chunks(chunks, dense_vectors, sparse_vectors)

        document.page_count = ingested.page_count
        document.ocr_used = ingested.ocr_used
        document.chunk_count = len(chunks)
        document.status = DocumentStatus.READY
        document.error_message = None
    except UnsupportedFileTypeError as e:
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
    except Exception as e:  # noqa: BLE001 — surface any ingestion failure on the document row
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)


@router.post("", response_model=DocumentUploadResponse)
def upload_document(
    file: UploadFile,
    title: str = Form(...),
    category: str | None = Form(None),
    is_public: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    settings = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    doc_id = str(uuid.uuid4())

    # Parsing needs a real local file path (every parser in app/ingestion/
    # takes file_path: str, none accept bytes) — write to a temp file for
    # that, upload it to R2 (the actual persistent storage), then discard
    # the temp copy. No permanent local file is ever created.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = Path(tmp.name)

    try:
        document = Document(
            id=doc_id,
            owner_id=current_user.id,
            filename=file.filename or f"{doc_id}{ext}",
            title=title.strip() or (file.filename or f"{doc_id}{ext}"),
            category=category,
            is_public=is_public,
            source_format=_source_format_for_ext(ext),
            size_bytes=tmp_path.stat().st_size,
            status=DocumentStatus.PROCESSING,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        _ingest_and_index(document, tmp_path, settings)
        storage.upload_file(tmp_path, storage.object_key(doc_id, ext))

        db.commit()
        db.refresh(document)
        return document
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    accessible_ids = get_accessible_doc_ids(current_user, db)
    if not accessible_ids:
        return []
    query = db.query(Document).filter(Document.id.in_(accessible_ids))
    if category:
        query = query.filter(Document.category == category)
    return query.order_by(Document.created_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = db.get(Document, document_id)
    # 404 (not 403) for an inaccessible doc — doesn't confirm it exists.
    if document is None or document.id not in get_accessible_doc_ids(current_user, db):
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/questions", response_model=list[QueryLogSummary])
def get_document_questions(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QueryLog]:
    document = db.get(Document, document_id)
    if document is None or document.id not in get_accessible_doc_ids(current_user, db):
        raise HTTPException(status_code=404, detail="Document not found")

    # Caller's own scoped questions only — same own-only pattern as every
    # other query-history endpoint (GET /queries etc.), not a new privacy
    # surface where other users' questions become visible.
    return (
        db.query(QueryLog)
        .filter(QueryLog.scoped_document_id == document_id, QueryLog.user_id == current_user.id)
        .order_by(QueryLog.created_at.desc())
        .limit(5)
        .all()
    )


_FILE_MEDIA_TYPES = {
    SourceFormat.PDF: "application/pdf",
    SourceFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    SourceFormat.MARKDOWN: "text/plain",
    SourceFormat.TEXT: "text/plain",
    SourceFormat.CSV: "text/csv",
}


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    document = db.get(Document, document_id)
    # 404 (not 403) for an inaccessible doc — same reasoning as get_document above.
    if document is None or document.id not in get_accessible_doc_ids(current_user, db):
        raise HTTPException(status_code=404, detail="Document not found")

    ext = Path(document.filename).suffix.lower()
    try:
        tmp_path = storage.download_to_temp(storage.object_key(document_id, ext), suffix=ext)
    except Exception as e:  # noqa: BLE001 — boto3 raises its own ClientError types
        raise HTTPException(status_code=404, detail="File not found in storage") from e

    # Cleanup happens after the response finishes streaming, not before —
    # FileResponse reads from this path lazily while sending the body.
    return FileResponse(
        tmp_path,
        media_type=_FILE_MEDIA_TYPES[document.source_format],
        background=BackgroundTask(tmp_path.unlink, missing_ok=True),
    )


@router.post("/{document_id}/share", status_code=204)
def share_document(
    document_id: str,
    request: ShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = _get_owned_document_or_404(document_id, db, current_user)

    target_user = db.query(User).filter(User.email == request.email).first()
    if target_user is None:
        raise HTTPException(status_code=404, detail="No user with that email")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You already own this document")

    existing = (
        db.query(DocumentShare)
        .filter(DocumentShare.document_id == document_id, DocumentShare.user_id == target_user.id)
        .first()
    )
    if existing is None:
        db.add(DocumentShare(document_id=document_id, user_id=target_user.id))
        db.commit()


def _get_owned_document_or_404(document_id: str, db: Session, current_user: User) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.owner_id != current_user.id:
        # 404, not 403 — same reasoning as share_document above.
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: str,
    request: DocumentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = _get_owned_document_or_404(document_id, db, current_user)

    if request.title is not None:
        stripped = request.title.strip()
        if not stripped:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        document.title = stripped
    if request.category is not None:
        document.category = request.category
    if request.is_public is not None:
        document.is_public = request.is_public

    db.commit()
    db.refresh(document)
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = _get_owned_document_or_404(document_id, db, current_user)

    db.query(DocumentShare).filter(DocumentShare.document_id == document_id).delete()
    delete_document_vectors(document_id)

    ext = Path(document.filename).suffix.lower()
    storage.delete_file(storage.object_key(document_id, ext))

    db.delete(document)
    db.commit()


@router.put("/{document_id}/content", response_model=DocumentOut)
def update_document_content(
    document_id: str,
    request: DocumentContentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = _get_owned_document_or_404(document_id, db, current_user)

    if document.source_format not in _TEXT_BACKED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Content editing isn't supported for {document.source_format.value} documents",
        )

    settings = get_settings()
    ext = Path(document.filename).suffix.lower()

    with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as tmp:
        tmp.write(request.content)
        tmp_path = Path(tmp.name)

    try:
        document.size_bytes = tmp_path.stat().st_size

        delete_document_vectors(document_id)
        document.status = DocumentStatus.PROCESSING
        db.commit()

        _ingest_and_index(document, tmp_path, settings)
        storage.upload_file(tmp_path, storage.object_key(document_id, ext))

        db.commit()
        db.refresh(document)
        return document
    finally:
        tmp_path.unlink(missing_ok=True)


def _source_format_for_ext(ext: str) -> SourceFormat:
    return {
        ".pdf": SourceFormat.PDF,
        ".docx": SourceFormat.DOCX,
        ".md": SourceFormat.MARKDOWN,
        ".markdown": SourceFormat.MARKDOWN,
        ".txt": SourceFormat.TEXT,
        ".csv": SourceFormat.CSV,
    }[ext]
