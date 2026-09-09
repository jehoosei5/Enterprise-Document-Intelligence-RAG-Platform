from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import QueryLog, User
from app.db.session import get_db
from app.schemas.queries import FeedbackRequest, QueryLogDetail, QueryLogSummary, StatsBucket, StatsResponse

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("", response_model=list[QueryLogSummary])
def list_queries(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[QueryLog]:
    return (
        db.query(QueryLog)
        .filter(QueryLog.user_id == current_user.id)
        .order_by(QueryLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/stats", response_model=StatsResponse)
def query_stats(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StatsResponse:
    since = datetime.utcnow() - timedelta(days=days)
    day = func.date(QueryLog.created_at)

    rows = (
        db.query(
            day.label("date"),
            func.count(QueryLog.id).label("query_count"),
            func.avg(QueryLog.faithfulness_score).label("avg_faithfulness"),
            func.avg(QueryLog.context_precision_score).label("avg_context_precision"),
            func.avg(QueryLog.answer_relevance_score).label("avg_answer_relevance"),
            func.avg(QueryLog.eval_passed).label("pass_rate"),  # MySQL treats tinyint(1) as numeric
            func.avg(
                case((QueryLog.feedback == "up", 1), (QueryLog.feedback == "down", 0), else_=None)
            ).label("thumbs_up_rate"),
            func.avg(QueryLog.latency_total_ms).label("avg_latency_total_ms"),
        )
        .filter(QueryLog.user_id == current_user.id, QueryLog.created_at >= since)
        .group_by(day)
        .order_by(day)
        .all()
    )

    buckets = [
        StatsBucket(
            date=r.date,
            query_count=r.query_count,
            avg_faithfulness=r.avg_faithfulness,
            avg_context_precision=r.avg_context_precision,
            avg_answer_relevance=r.avg_answer_relevance,
            pass_rate=r.pass_rate,
            thumbs_up_rate=r.thumbs_up_rate,
            avg_latency_total_ms=r.avg_latency_total_ms or 0,
        )
        for r in rows
    ]
    return StatsResponse(buckets=buckets)


@router.get("/{query_id}", response_model=QueryLogDetail)
def get_query(
    query_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryLog:
    log = db.get(QueryLog, query_id)
    if log is None or log.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Query not found")
    return log


@router.post("/{query_id}/feedback", status_code=204)
def submit_feedback(
    query_id: str,
    request: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    log = db.get(QueryLog, query_id)
    if log is None or log.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Query not found")

    log.feedback = request.rating  # overwrites any prior rating
    db.commit()
