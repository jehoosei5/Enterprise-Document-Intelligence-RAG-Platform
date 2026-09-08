from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, health, query
from app.retrieval.qdrant_store import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_collection()
    yield


app = FastAPI(title="Enterprise Document Intelligence & RAG Platform", lifespan=lifespan)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(query.router)
