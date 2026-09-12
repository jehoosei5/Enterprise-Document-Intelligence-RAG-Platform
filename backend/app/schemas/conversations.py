from datetime import datetime

from pydantic import BaseModel

from app.schemas.query import SourceOut


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: datetime


class ConversationTurn(BaseModel):
    query_id: str
    question: str
    answer: str
    sources: list[SourceOut]
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    turns: list[ConversationTurn]
