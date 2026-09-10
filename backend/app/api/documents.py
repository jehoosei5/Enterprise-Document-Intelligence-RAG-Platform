import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_accessible_doc_ids, get_current_user
from app.chunking.chunker import chunk_document
from app.core.config import get_settings
from app.db.models import Document, DocumentShare, DocumentStatus, SourceFormat, User
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_texts
from app.embeddings.sparse_embeddings import embed_texts as sparse_embed_texts
from app.ingestion.dispatch import SUPPORTED_EXTENSIONS, UnsupportedFileTypeError, parse_document
from app.retrieval.qdrant_store import upsert_chunks
from app.schemas.documents import DocumentOut, DocumentUploadResponse, ShareRequest

router = APIRouter(prefix="/documents", tags=["documents"])


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
    dest_path = settings.upload_path / f"{doc_id}{ext}"
    with dest_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    document = Document(
        id=doc_id,
        owner_id=current_user.id,
        filename=file.filename or dest_path.name,
        title=title.strip() or (file.filename or dest_path.name),
        category=category,
        is_public=is_public,
        source_format=_source_format_for_ext(ext),
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        ingested = parse_document(str(dest_path), doc_id=doc_id, filename=document.filename)
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

    db.commit()
    db.refresh(document)
    return document


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


@router.post("/{document_id}/share", status_code=204)
def share_document(
    document_id: str,
    request: ShareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = db.get(Document, document_id)
    if document is None or document.owner_id != current_user.id:
        # 404, not 403 — same reasoning as get_document above.
        raise HTTPException(status_code=404, detail="Document not found")

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


def _source_format_for_ext(ext: str) -> SourceFormat:
    return {
        ".pdf": SourceFormat.PDF,
        ".docx": SourceFormat.DOCX,
        ".md": SourceFormat.MARKDOWN,
        ".markdown": SourceFormat.MARKDOWN,
        ".txt": SourceFormat.TEXT,
        ".csv": SourceFormat.CSV,
    }[ext]
