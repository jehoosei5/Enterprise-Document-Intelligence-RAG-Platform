from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceOut(BaseModel):
    index: int
    filename: str
    locator: str
    text: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    input_tokens: int
    output_tokens: int
