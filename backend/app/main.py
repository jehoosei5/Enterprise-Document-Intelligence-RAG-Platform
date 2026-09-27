from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, conversations, documents, health, queries, query
from app.core.config import get_settings
from app.retrieval.qdrant_store import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_collection()
    yield


app = FastAPI(title="Enterprise Document Intelligence & RAG Platform", lifespan=lifespan)

# Browser fetch() calls from the frontend's origin need CORS headers, or
# they fail in-browser even though curl/server-to-server calls work fine
# (curl doesn't enforce CORS). frontend_base_url already exists for
# building password-reset links; reused here as the allowed origin —
# matches the Vite dev server's fixed port (see frontend/vite.config.ts)
# and what's authorized for the Google OAuth Client ID in Google Cloud
# Console.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(queries.router)
app.include_router(conversations.router)
