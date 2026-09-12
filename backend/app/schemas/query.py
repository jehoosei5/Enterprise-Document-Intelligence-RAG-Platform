from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)
    evaluate: bool = True
    conversation_id: str | None = None
    # When set, retrieval is restricted to just this one document (the
    # "Ask about this document" panel on the viewer page) instead of
    # everything the caller can access.
    document_id: str | None = None


class SourceOut(BaseModel):
    index: int
    filename: str
    locator: str
    text: str


class QueryResponse(BaseModel):
    query_id: str
    conversation_id: str
    answer: str
    sources: list[SourceOut]
    rewritten_query: str
    input_tokens: int
    output_tokens: int
