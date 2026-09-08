import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.chunking.chunker import chunk_document
from app.core.config import get_settings
from app.db.models import Document, DocumentStatus, SourceFormat
from app.db.session import get_db
from app.embeddings.azure_embeddings import embed_texts
from app.embeddings.sparse_embeddings import embed_texts as sparse_embed_texts
from app.ingestion.dispatch import SUPPORTED_EXTENSIONS, UnsupportedFileTypeError, parse_document
from app.retrieval.qdrant_store import upsert_chunks
from app.schemas.documents import DocumentOut, DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentUploadResponse)
def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> Document:
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
        filename=file.filename or dest_path.name,
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
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _source_format_for_ext(ext: str) -> SourceFormat:
    return {
        ".pdf": SourceFormat.PDF,
        ".docx": SourceFormat.DOCX,
        ".md": SourceFormat.MARKDOWN,
        ".markdown": SourceFormat.MARKDOWN,
        ".txt": SourceFormat.TEXT,
        ".csv": SourceFormat.CSV,
    }[ext]
