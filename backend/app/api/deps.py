"""Shared FastAPI dependencies: current-user auth and document-access checks."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.models import Document, DocumentShare, User
from app.db.session import get_db


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


def get_accessible_doc_ids(user: User, db: Session) -> list[str]:
    """Documents the user owns, unioned with documents shared with them and
    documents marked visible to everyone at the company.
    """
    owned = db.scalars(select(Document.id).where(Document.owner_id == user.id)).all()
    shared = db.scalars(select(DocumentShare.document_id).where(DocumentShare.user_id == user.id)).all()
    public = db.scalars(select(Document.id).where(Document.is_public.is_(True))).all()
    return list({*owned, *shared, *public})
