from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.retrieval.qdrant_store import get_client
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    checks = {"database": "ok", "qdrant": "ok"}

    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        settings = get_settings()
        get_client().get_collection(settings.qdrant_collection_name)
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
