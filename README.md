# Enterprise Document Intelligence & RAG Platform

A production-style retrieval-augmented generation (RAG) system. Users upload
documents (PDF, DOCX, Markdown, plain text/CSV) and ask questions against
them, with answers grounded in cited sources, gated by auth/permissions, and
continuously evaluated for faithfulness.

Unlike a basic "PDF → embeddings → chatbot" project, this covers the full
production surface: multi-format ingestion, hybrid retrieval with reranking,
access control, and — the differentiator — a hallucination/faithfulness
evaluation system with a per-query debug trace, not just a working demo.

**Core pipeline:**

```
Upload → parse (format-specific) → chunk → embed + index (vector + keyword)
       → query rewrite → hybrid retrieve → rerank → generate with citations
       → evaluate → log/serve
```

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, hand-rolled pipeline (no LangChain/LlamaIndex) |
| LLM (generation, query rewriting, embeddings) | Azure OpenAI |
| Reranker | Cohere Rerank API |
| Vector + hybrid (dense + sparse/BM25) search | Qdrant Cloud |
| Relational store (users, documents, permissions, eval logs) | Postgres on Railway |
| Frontend | React + Vite + TypeScript |

No local infra is required to run this beyond the backend/frontend
processes themselves — Postgres, Qdrant, Azure OpenAI, and Cohere are all
managed/cloud services, configured via environment variables.

## Project structure

```
backend/
  app/
    api/           # FastAPI routers
    core/          # config, settings
    ingestion/      # format-specific parsers -> common intermediate representation
    chunking/       # structure-aware / fixed-size chunkers
    embeddings/     # Azure OpenAI embedding client
    retrieval/      # Qdrant hybrid search, query rewriting, reranking
    generation/     # LLM answer generation with citations
    db/             # SQLAlchemy models, session
    schemas/        # Pydantic request/response models
  alembic/          # DB migrations
  tests/
frontend/           # React + Vite + TS app (chat UI + eval/debug dashboard)
```

## Setup

1. Copy `.env.example` to `.env` and fill in:
   - Azure OpenAI endpoint, API key, and deployment names (chat + embeddings)
   - Qdrant Cloud URL + API key
   - Cohere API key
   - Railway Postgres `DATABASE_URL`
   - A JWT secret (for v3 auth)
2. Backend:
   ```
   cd backend
   python -m venv venv
   venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```
3. Frontend (added once scaffolded): `cd frontend && npm install`

## Build plan

**v1 — Core RAG pipeline**
- Multi-format ingestion: PDF (+ OCR fallback for scans), DOCX, Markdown,
  plain text/CSV — each parsed into a common intermediate representation
  (text, section/page, source metadata)
- Structure-aware chunking where possible (headers for MD/DOCX, not blind
  fixed-size)
- Embeddings → vector DB
- Basic retrieval → LLM generation with citations (page/section/line-range
  depending on format)

**v2 — Retrieval quality**
- Query rewriting
- Hybrid search: vector + BM25 in parallel (Qdrant dense + sparse vectors)
- Reranker (Cohere) narrows combined results to top-k

**v3 — Access control**
- Authentication
- Document-level permissions gating retrieval

**v4a — Evaluation (the differentiator — don't skip or rush this)**
- Faithfulness/hallucination scoring, context precision, answer relevance
  (RAGAS-style), logged per query
- Aggregate eval dashboard (trends over time)
- Per-query debug view, toggleable:
  - User query + rewritten query (diffed)
  - Retrieval: vector + BM25 result counts, top chunks with
    similarity/BM25 scores pre-rerank
  - Reranking: which chunks survived, with cross-encoder/Cohere scores
  - Sources: document + page/section per cited chunk
  - Generation: model, input/output tokens, estimated cost
  - Evaluation: faithfulness/context precision/answer relevance, with a
    pass/fail threshold flag (e.g. faithfulness < 0.7 → flagged)
  - Latency breakdown: retrieval, reranking, LLM, total

**v4b — Polish (cut first if time runs short)**
- Conversation memory (multi-turn, follow-up resolution)
- Streaming responses
- Cost/latency tracking surfaced in the main UI (not just debug view)
- User feedback (thumbs up/down) feeding back into eval data
