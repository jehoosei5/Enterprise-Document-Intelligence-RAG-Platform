from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Conversation, QueryLog, User
from app.db.session import get_db
from app.schemas.conversations import ConversationDetail, ConversationSummary, ConversationTurn

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConversationSummary]:
    rows = (
        db.query(Conversation, func.count(QueryLog.id))
        .outerjoin(QueryLog, QueryLog.conversation_id == Conversation.id)
        .filter(Conversation.user_id == current_user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ConversationSummary(
            id=conv.id, title=conv.title, message_count=count, created_at=conv.created_at
        )
        for conv, count in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetail:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    logs = (
        db.query(QueryLog)
        .filter(QueryLog.conversation_id == conversation_id)
        .order_by(QueryLog.created_at)
        .all()
    )
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        turns=[
            ConversationTurn(
                query_id=log.id, question=log.question, answer=log.answer, created_at=log.created_at
            )
            for log in logs
        ],
    )
