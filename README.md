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

**Status: v1 (core pipeline), v2 (retrieval quality), and v3 (access
control) are built and verified.** v4a–v4b are not started yet — see
[Build plan](#build-plan).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, hand-rolled pipeline (no LangChain/LlamaIndex) |
| LLM (generation, query rewriting, embeddings) | Azure OpenAI |
| Reranker | Cohere Rerank API |
| Vector + hybrid (dense + sparse/BM25) search | Qdrant Cloud |
| Relational store (users, documents, permissions, eval logs) | MySQL — local for dev, Railway once deployed |
| Frontend | React + Vite + TypeScript (not started — v1 is API-only) |

No local infra is required beyond a local MySQL install for dev — Qdrant,
Azure OpenAI, and Cohere are all managed/cloud services, configured via
environment variables.

## Project structure

```
backend/
  app/
    core/
      config.py            # pydantic-settings, reads backend/.env
      security.py            # bcrypt password hashing + JWT (raw bcrypt — passlib is broken, see below)
    db/                   # SQLAlchemy models (User, Document, DocumentShare) + session
    ingestion/             # format-specific parsers -> common IR (common.py)
      pdf.py                 # PyMuPDF + pytesseract OCR fallback for scans
      docx_parser.py          # python-docx, heading-aware
      markdown_parser.py      # markdown-it-py, heading-aware
      text_csv.py             # plain text (line ranges) + CSV (row ranges)
      dispatch.py             # picks parser by file extension
    chunking/chunker.py    # structure-aware (MD/DOCX) + fixed-size (PDF/text/CSV)
    embeddings/
      azure_embeddings.py     # Azure OpenAI dense embeddings, auto-detects dimension
      sparse_embeddings.py     # local BM25 sparse vectors via fastembed (Qdrant/bm25)
    retrieval/
      qdrant_store.py          # collection mgmt (dense+sparse), upsert, dense + RRF hybrid search
      query_rewrite.py          # single-turn query rewrite (Azure OpenAI)
      reranker.py                # Cohere cross-encoder rerank, fails open to fused order
    generation/generator.py    # Azure OpenAI chat + [n]-citation mapping
    api/
      auth.py                  # register/login/me
      deps.py                   # get_current_user, get_accessible_doc_ids (owned ∪ shared)
      documents.py, query.py, health.py
    schemas/                # Pydantic request/response models
    main.py                 # FastAPI app + router wiring
  alembic/                # DB migrations
  tests/                  # pytest unit tests (ingestion, chunking) + fixtures/
  requirements.txt
  .env.example / .env     # .env is git-ignored
frontend/                 # not started yet (v1 is backend/API-only)
```

## Setup

1. **Environment variables** — copy `backend/.env.example` to `backend/.env`
   and fill in:
   - Azure OpenAI endpoint, API key, and deployment names (chat + embeddings)
   - Qdrant Cloud URL + API key
   - Cohere API key (used for reranking)
   - `DATABASE_URL` — for local dev, point at a local MySQL instance
     (`mysql+pymysql://root:<password>@localhost:3306/ragdb`, after running
     `CREATE DATABASE ragdb;`); once deployed on Railway, the backend
     service's own env vars should reference the MySQL plugin's internal
     URL instead (`mysql.railway.internal` only resolves inside Railway's
     private network, not from your machine)
   - A JWT secret (used to sign access tokens — set this to a real random
     string, not the placeholder)

2. **Backend**:
   ```
   cd backend
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   alembic upgrade head            # creates users, documents, document_shares tables
   venv\Scripts\uvicorn.exe app.main:app --reload
   ```
   > If a bare `uvicorn` command picks up a different Python (e.g. Anaconda)
   > even after activating the venv, call `venv\Scripts\uvicorn.exe`
   > directly — it bypasses `PATH` resolution entirely.

3. **Tests** (pure unit tests, no external API calls):
   ```
   venv\Scripts\pytest.exe tests/ -v
   ```

4. **Frontend**: not built yet — v1 is backend/API-only, verified via
   `pytest` + `curl`.

### API

All endpoints except `/health`, `/auth/register`, and `/auth/login` require
`Authorization: Bearer <token>` (obtained from `/auth/login`).

| Endpoint | Purpose |
|---|---|
| `GET /health` | DB + Qdrant connectivity check (no auth) |
| `POST /auth/register` | `{"email": ..., "password": ...}` → create a user (no auth) |
| `POST /auth/login` | `{"email": ..., "password": ...}` → `{"access_token": ..., "token_type": "bearer"}` (no auth) |
| `GET /auth/me` | Current user's profile |
| `POST /documents` | Upload a file (`multipart/form-data`, field `file`) — parses, chunks, embeds (dense + sparse), indexes, and returns the document record. Caller becomes the owner |
| `GET /documents` | List documents the caller owns or has been shared |
| `GET /documents/{id}` | Get one document's status (404 if inaccessible) |
| `POST /documents/{id}/share` | `{"email": "..."}` — owner-only, grants that user read access |
| `POST /query` | `{"question": "...", "top_k": 5}` → query is rewritten, hybrid-retrieved (dense+BM25, fused via Qdrant RRF, filtered to the caller's accessible documents), reranked (Cohere), then answered with `[n]` citations. Response includes `rewritten_query` alongside `answer`/`sources` |

## Build plan

**v1 — Core RAG pipeline ✅ done**
- Multi-format ingestion: PDF (+ OCR fallback for scans — needs the
  Tesseract binary installed separately, not yet present on the dev
  machine), DOCX, Markdown, plain text/CSV — each parsed into a common
  intermediate representation (text, section/page, source metadata)
- Structure-aware chunking where possible (headers for MD/DOCX), page-safe
  fixed-size chunking for PDF/text/CSV
- Embeddings (Azure OpenAI, dimension auto-detected) → Qdrant (dense +
  reserved sparse vector slot for v2)
- Retrieval → LLM generation with inline citations (page/section/line-range/
  row-range depending on format)
- MySQL tracks document-level metadata only; Qdrant payload is the source
  of truth for chunk text + citation locators
- Verified end-to-end against real Azure OpenAI, Qdrant Cloud, and local
  MySQL: all 5 formats upload successfully, and `/query` answers are
  correctly grounded and cited to the right document/location

**v2 — Retrieval quality ✅ done**
- Query rewriting: single-turn Azure OpenAI call (typo/acronym cleanup,
  makes intent explicit) — not conversation-aware, that's v4b's job. Used
  for retrieval only; generation still answers the user's original wording
- Hybrid search: dense (Azure OpenAI embeddings) + sparse BM25
  (`fastembed`'s `Qdrant/bm25`, local, no API key) fused server-side via
  Qdrant's Query API (`prefetch` + Reciprocal Rank Fusion) in one call
- Reranker: Cohere cross-encoder narrows the fused candidates
  (`hybrid_fetch_k`, default 20) down to the final `top_k` (default 5);
  both query rewrite and rerank fail open (fall back to unmodified
  query / fused order) rather than failing the request
- Verified end-to-end: hybrid fusion smoke-tested directly against Qdrant,
  reranker confirmed to actually reorder by relevance, paraphrased and
  keyword-heavy queries both retrieve correctly via `/query`, and a bad
  Cohere key confirmed to degrade gracefully instead of erroring

**v3 — Access control ✅ done**
- Authentication: JWT bearer tokens (`pyjwt`), password hashing via raw
  `bcrypt` (**`passlib[bcrypt]` was dropped** — verified incompatible with
  the installed `bcrypt>=4.1`, crashes on `hash()`)
- Permission model: `documents.owner_id` (uploader) + a `document_shares`
  table (explicit per-user read grants) — no roles/admin tier
- Enforced at retrieval time, not just listing: the caller's accessible
  `doc_id`s are computed from MySQL and passed as a Qdrant filter into
  *both* hybrid sub-queries, so inaccessible chunks are never retrieved in
  the first place, not merely hidden after the fact
- `GET /documents/{id}` and `POST /documents/{id}/share` on an inaccessible
  document both return 404 (never 403), so a caller can't learn a document
  exists just by trying
- Verified end-to-end: two real users, cross-user isolation on both
  `GET /documents` and `POST /query`, sharing grants access, non-owner
  share attempts rejected, all protected routes 401 without a token,
  `/health` still open
- Caught along the way: Qdrant needs an explicit payload index on `doc_id`
  to filter by it (`ensure_collection()` now creates one) — filtering
  without it is a 400, not silently ignored

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
