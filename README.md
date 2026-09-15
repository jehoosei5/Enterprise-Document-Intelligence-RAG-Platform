# Enterprise Document Intelligence & RAG Platform

A production-style retrieval-augmented generation (RAG) system. Users upload
documents (PDF, DOCX, Markdown, plain text/CSV) and ask questions against
them, with answers grounded in cited sources, gated by auth/permissions, and
continuously evaluated for faithfulness.

Unlike a basic "PDF → embeddings → chatbot" project, this covers the full
production surface: multi-format ingestion, hybrid retrieval with reranking,
access control, a hallucination/faithfulness evaluation system with a
per-query debug trace, and a real frontend on top — not just a working demo.

**Core pipeline:**

```
Upload → parse (format-specific) → chunk → embed + index (vector + keyword)
       → query rewrite → hybrid retrieve → rerank → generate with citations
       → evaluate → log/serve
```

**Status: v1–v4b (the original brief) are all built and verified.** On top
of that, auth/document management has since grown well past the brief —
Google sign-in, password reset, persistent file storage, document
metadata/visibility, and a full React frontend. See [Build plan](#build-plan)
and [Beyond the brief](#beyond-the-brief).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python + FastAPI, hand-rolled pipeline (no LangChain/LlamaIndex) |
| LLM (generation, query rewriting, embeddings) | Azure OpenAI |
| Reranker | Cohere Rerank API |
| Vector + hybrid (dense + sparse/BM25) search | Qdrant Cloud |
| Relational store (users, documents, permissions, eval logs) | MySQL — local for dev, Railway once deployed |
| Original file storage | Cloudflare R2 (S3-compatible, via boto3) — survives redeploys, unlike Railway's ephemeral container disk |
| Auth | JWT (bearer tokens) + Google Identity Services sign-in; bcrypt password hashing |
| Transactional email | Resend (password-reset links) |
| Frontend | React 19 + Vite + TypeScript + Tailwind CSS, in its own repo (`DocIntel-frontend`) |

Qdrant, Azure OpenAI, Cohere, Cloudflare R2, and Resend are all managed/cloud
services, configured via environment variables — no local infra required
beyond a local MySQL install for dev.

## Project structure

```
backend/
  app/
    core/
      config.py            # pydantic-settings, reads backend/.env
      security.py            # bcrypt hashing + JWT + Google ID-token verification + reset-token hashing
      email.py                # Resend transactional email (password reset), fails open/silent
      storage.py               # Cloudflare R2 (S3-compatible) original-file storage, the only module touching boto3
    db/                   # SQLAlchemy models (User, Document, DocumentShare, Conversation, QueryLog) + session
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
      qdrant_store.py          # collection mgmt (dense+sparse), dense/sparse/RRF-hybrid search
      query_rewrite.py          # query rewrite + needs_retrieval classification (Azure OpenAI), conversation-history-aware follow-up resolution
      reranker.py                # Cohere cross-encoder rerank, fails open to fused order
    generation/generator.py    # Azure OpenAI chat (sync + streaming), [n]-citation mapping, plain conversational replies, conversation-title generation
    evaluation/metrics.py      # hand-rolled RAGAS-style faithfulness/context-precision/answer-relevance
    api/
      auth.py                  # register/login/me + Google sign-in + forgot/reset password
      deps.py                   # get_current_user, get_accessible_doc_ids (owned ∪ shared ∪ public)
      documents.py               # upload (title/category/visibility), list/get, share, patch, delete,
                                    original-file download, content editing (text-backed formats),
                                    per-document recent-questions history
      query.py (sync + SSE streaming), queries.py (eval history/feedback/dashboard),
      conversations.py, health.py
    schemas/                # Pydantic request/response models
    main.py                 # FastAPI app + CORS middleware + router wiring
  alembic/                # DB migrations
  tests/                  # pytest unit tests (ingestion, chunking, metrics, security) + fixtures/
  requirements.txt
  .env.example / .env     # .env is git-ignored

DocIntel-frontend/frontend/     # separate repo — React 19 + Vite + TS + Tailwind
  src/
    pages/
      LoginPage.tsx          # email/password + Google sign-in, forgot/reset password
      DocumentsPage.tsx        # browse/search/filter by category, share, edit metadata, delete
      UploadPage.tsx            # upload with title/category/visibility
      DocumentViewerPage.tsx     # renders PDF (pdfjs-dist)/DOCX (mammoth)/MD (markdown-it)/TXT/CSV inline,
                                    in-place text content editing, in-document search highlighting (mark.js),
                                    "ask about this document" scoped Q&A panel with recent-questions history
      ChatPage.tsx                # conversational Q&A: streaming answers, inline citations, thumbs up/down
                                    feedback, conversation history/switching
    components/  Sidebar.tsx, RequireAuth.tsx (route guard)
    lib/         api.ts (fetch wrapper), auth.ts, documents.ts, query.ts, conversations.ts,
                 googleIdentity.ts, categories.ts, csv.ts
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
   - `GOOGLE_CLIENT_ID` — a Google Cloud Console OAuth Client ID (Web
     application type), authorized for the frontend's exact dev origin
     (`http://localhost:5174`). No client secret needed — the backend only
     verifies client-obtained ID tokens
   - `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_ENDPOINT` /
     `R2_BUCKET_NAME` — a Cloudflare R2 bucket + API token, for storing
     original uploaded files (survives redeploys, unlike local disk)
   - `RESEND_API_KEY` (+ `RESEND_FROM_EMAIL`) — for password-reset emails;
     without a verified sending domain, Resend's sandbox limit only
     delivers to the account's own signup address
   - `FRONTEND_BASE_URL` — the frontend's origin. Used both to build
     password-reset links and as the CORS-allowed origin, so it must match
     wherever the frontend is actually running (`http://localhost:5174` for
     local dev — fixed via `strictPort` in `vite.config.ts`)

2. **Backend**:
   ```
   cd backend
   python -m venv venv
   venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   alembic upgrade head            # creates/updates users, documents, document_shares, conversations, query_logs tables
   venv\Scripts\uvicorn.exe app.main:app --reload
   ```
   > If a bare `uvicorn` command picks up a different Python (e.g. Anaconda)
   > even after activating the venv, call `venv\Scripts\uvicorn.exe`
   > directly — it bypasses `PATH` resolution entirely.

3. **Tests** (pure unit tests, no external API calls):
   ```
   venv\Scripts\pytest.exe tests/ -v
   ```

4. **Frontend** (separate repo, `DocIntel-frontend/frontend`):
   ```
   cd frontend
   npm install
   npm run dev            # Vite dev server, fixed at http://localhost:5174
   ```
   Set `VITE_API_BASE_URL` (defaults to `http://localhost:8000`) if the
   backend isn't running on its default port.

### API

All endpoints except `/health`, `/auth/register`, `/auth/login`,
`/auth/google`, `/auth/forgot-password`, and `/auth/reset-password` require
`Authorization: Bearer <token>` (obtained from `/auth/login` or
`/auth/google`).

| Endpoint | Purpose |
|---|---|
| `GET /health` | DB + Qdrant connectivity check (no auth) |
| `POST /auth/register` | `{"email": ..., "password": ...}` → create a user (no auth) |
| `POST /auth/login` | `{"email": ..., "password": ...}` → `{"access_token": ..., "token_type": "bearer"}` (no auth) |
| `POST /auth/google` | `{"id_token": ...}` — verifies a Google Identity Services ID token, then logs in, links to an existing password account by verified email, or creates a new account (no auth) |
| `POST /auth/forgot-password` | `{"email": ...}` — always returns the same generic response (never reveals whether the account exists); emails a reset link when it does and has a password set (no auth) |
| `POST /auth/reset-password` | `{"token": ..., "new_password": ...}` — sets a new password if the token is valid and unexpired (no auth) |
| `GET /auth/me` | Current user's profile |
| `POST /documents` | Upload a file (`multipart/form-data`: `file`, `title`, optional `category`, `is_public`, optional `confirm_different_type`, optional `rename_to`) — parses, chunks, embeds (dense + sparse), indexes, stores the original file in R2, and returns the document record. Caller becomes the owner. Duplicate check (owner-scoped, case-insensitive stem): same name + same type → **409** `duplicate_exact` (must rename); same name + different type → **409** `duplicate_name_different_type` unless retried with `confirm_different_type=true` (accept) or `rename_to=...` |
| `GET /documents` | List documents the caller owns, has been shared, or that are marked public (optionally filtered by `category`) |
| `GET /documents/{id}` | Get one document's status (404 if inaccessible) |
| `GET /documents/{id}/file` | Stream the original uploaded file back from R2 (404 if inaccessible or missing from storage) |
| `GET /documents/{id}/questions` | The caller's own 5 most recent questions asked via that document's scoped "ask about this document" panel |
| `PATCH /documents/{id}` | `{"title"?, "category"?, "is_public"?}` — owner-only, partial update |
| `PUT /documents/{id}/content` | `{"content": "..."}` — owner-only, replaces a text-backed document's (text/Markdown/CSV) content and re-parses/re-chunks/re-embeds/re-indexes it in place |
| `DELETE /documents/{id}` | Owner-only — removes the document row, its shares, its Qdrant vectors, and its R2 file |
| `POST /documents/{id}/share` | `{"email": "..."}` — owner-only, grants that user read access |
| `POST /query` | `{"question": "...", "top_k": 5, "evaluate": true, "conversation_id": null, "document_id": null}` → query is classified as conversational vs. retrieval-worthy and rewritten (follow-up-aware if `conversation_id` has prior turns); if retrieval-worthy: hybrid-retrieved (dense+BM25, fused via Qdrant RRF, filtered to the caller's accessible documents, or scoped to just `document_id` when given), reranked (Cohere), answered with `[n]` citations, then scored and logged; a purely conversational message (greeting, thanks, etc.) instead gets a plain chat reply, skipping retrieval/rerank/citations entirely. Response includes `query_id`, `conversation_id` (created if omitted), `rewritten_query`, `answer`, `sources`. A new conversation's title is generated from the first turn in a background task after the response is sent |
| `POST /query/stream` | Same request/behavior as `/query`, but the answer streams as Server-Sent Events (`data: {"delta": "..."}`) as it's generated, ending with one `data: {"event": "done", ...}` carrying the same structured metadata (`query_id`, `sources`, tokens, eval scores) |
| `GET /queries` | Paginated list of the caller's own past queries (summary + eval scores + feedback) |
| `GET /queries/{id}` | Full per-query debug trace: dense/sparse/fused/reranked candidates with scores, sources, tokens, eval scores + detail (claims, verdicts, hypothetical questions), feedback, latency breakdown. 404 if not the caller's own |
| `POST /queries/{id}/feedback` | `{"rating": "up"|"down"}` — owner-only, overwrites any prior rating |
| `GET /queries/stats?days=30` | Daily aggregates for the caller: query count, avg eval scores, pass rate, thumbs-up rate, avg latency — the eval dashboard's data source |
| `GET /conversations` | Paginated list of the caller's own conversations (title, message count) |
| `GET /conversations/{id}` | Full ordered turn history (question/answer/query_id per turn) for one conversation. 404 if not the caller's own |

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

**v4a — Evaluation (the differentiator) ✅ done**
- Hand-rolled RAGAS-style metrics against Azure OpenAI directly (not the
  `ragas` package — it pulls in LangChain, contradicting this project's
  no-LangChain/full-debug-visibility stance):
  - **Faithfulness**: claim-extraction call + per-claim verdict-against-
    context call. Score = supported/total claims
  - **Context precision**: per-context relevance verdicts against the
    question, rank-weighted (mean of precision@k over relevant positions —
    rewards relevant chunks ranked earlier, not just present)
  - **Answer relevance**: generates hypothetical questions the answer
    would address, scores mean cosine similarity to the actual question
  - All three computed against the chunks actually used for generation
    (post-rerank); each fails open independently (`None` on error, logged)
    rather than 500ing `/query`
- `evaluate: bool` on `/query` (default `true`) to skip eval when not
  needed (saves ~3 LLM calls of latency/cost)
- Per-query debug trace (`GET /queries/{id}`), fetched on demand rather
  than inlined in every response:
  - Rewritten query, dense-only + sparse-only + fused pre-rerank
    candidates (with their native similarity/BM25/RRF scores — not just
    the fused score, which alone can't show what each retrieval method
    contributed), reranked chunks (visibly reordered vs. the fused order),
    cited sources, tokens, eval scores + full detail (claims, verdicts,
    hypothetical questions), and a 5-way latency breakdown (retrieval,
    rerank, LLM, eval, total)
- Aggregate dashboard (`GET /queries/stats`) — daily avg scores, pass
  rate, avg latency, scoped to the caller (no admin role exists, so eval
  history stays permission-scoped like documents)
- Dollar cost estimation explicitly deferred (no live Azure pricing
  available) — token counts are tracked, not converted to $
- Verified end-to-end: a well-grounded answer scored faithfulness 1.0 /
  context precision 0.83; a deliberately fabricated claim was caught
  (faithfulness dropped to 0.33, correctly flagging the 2 unsupported
  claims); an unanswerable question showed the metrics' real value —
  faithfulness stayed 1.0 (the model honestly declined rather than
  hallucinating) while context precision correctly dropped to 0.0
  (nothing retrieved was actually relevant); reranking visibly reordered
  the fused candidates; cross-user access to another user's query log
  returned 404

**v4b — Polish ✅ done**
- **Conversation memory**: every query belongs to a `Conversation` (even a
  standalone one gets one, of length 1 — no special-casing). Follow-up
  resolution is one extra bit of context on the existing query-rewrite call
  (`rewrite_query(question, history=...)`, capped to the last
  `conversation_history_turns` turns), not a separate pipeline stage.
  "Cost/latency surfaced in the main UI" was dropped — no frontend existed
  yet to surface it in (since built — see [Beyond the brief](#beyond-the-brief))
- **Streaming**: `POST /query/stream` (SSE) — retrieval/rerank happen up
  front as usual, only generation streams token-by-token (`stream=True`,
  `stream_options={"include_usage": True}` for token counts from the final
  chunk). Citation parsing, eval, and persistence still run after the
  stream completes, ending in one final structured SSE event — a real UX
  tradeoff (eval latency lands as a pause *after* the visible text, not
  hidden by streaming it away)
- **Feedback**: `POST /queries/{id}/feedback` (`"up"`/`"down"`, overwritable),
  surfaced as a daily `thumbs_up_rate` in `GET /queries/stats` alongside
  the eval-score trends
- Verified end-to-end: a follow-up question ("how do I request it" after
  asking about PTO days) correctly resolved via conversation history and
  retrieved the right chunk; `/query/stream` delivered real incremental
  tokens ending in a metadata event with populated eval scores, and its
  `QueryLog` persisted identically to the non-streaming path; feedback
  overwrite and its dashboard aggregation both confirmed; cross-user access
  to another user's conversation or query feedback returned 404

## Beyond the brief

Everything below goes past the original v1–v4b brief (`Overview.txt`) —
turning the API into a real product with a UI in front of it.

- **Google sign-in**: `POST /auth/google` verifies a Google Identity
  Services ID token server-side (signature, audience, expiry) and either
  logs in an existing Google-linked account, links Google to an existing
  password account by verified email, or creates a new account. An
  account's `hashed_password` and `google_sub` are independent capability
  flags, not a single provider enum — either, both, or (transiently)
  neither can be set
- **Password reset**: `POST /auth/forgot-password` + `POST
  /auth/reset-password`, email delivered via Resend. Only the SHA-256 hash
  of the reset token is stored (one active reset at a time, overwritten by
  each new request); the forgot-password response is identical whether or
  not the account exists or has a password, to avoid account enumeration
- **CORS**: the frontend's origin is explicitly allowlisted
  (`CORSMiddleware`), since browser `fetch()` enforces it even though
  server-to-server/`curl` calls never hit the restriction
- **Document metadata & visibility**: documents now have an editable
  `title` (defaults to filename), an optional `category` (for
  browsing/filtering), and `is_public` — a public document is visible to
  every user, not just the owner and explicit shares. `get_accessible_doc_ids`
  now unions owned ∪ shared ∪ public, and that union is what's enforced at
  retrieval time, not just listing
- **Persistent file storage**: original uploaded files are stored in
  Cloudflare R2 (`app/core/storage.py`, the only module touching `boto3`
  directly) rather than local disk — Railway's container filesystem is
  ephemeral and wipes on every redeploy. `GET /documents/{id}/file`
  streams a document's original file back out for the frontend's
  in-browser viewer
- **In-place content editing**: text-backed documents (plain text,
  Markdown, CSV) can have their content replaced via `PUT
  /documents/{id}/content`, which re-parses/chunks/embeds/indexes and
  re-uploads to R2 in one step — reusing the same ingestion path as upload
- **Conversational vs. retrieval-worthy classification**: query rewriting
  now also decides, via the model's own judgment (not a keyword list),
  whether a message needs document retrieval at all — a greeting or
  "thanks" gets a plain chat reply instead of running retrieval/rerank/
  citations/eval for no reason
- **Document-scoped queries & per-document Q&A history**: `POST /query`
  accepts an optional `document_id` to restrict retrieval to one document
  (the viewer page's "ask about this document" panel); `GET
  /documents/{id}/questions` surfaces the caller's 5 most recent questions
  asked that way
- **Background conversation titling**: a new conversation's title
  (initially just the first question, truncated) is upgraded to an
  LLM-generated one in a `BackgroundTask` after the response has already
  gone out, so it never adds latency to the user-facing request
- **Frontend** (`DocIntel-frontend/frontend`, a separate repo): React 19 +
  Vite + TypeScript + Tailwind CSS. Login (password + Google + forgot/reset
  password), a documents browser (search/filter by category, share, edit
  metadata, delete), upload, an in-browser document viewer (PDF via
  `pdfjs-dist`, DOCX via `mammoth`, Markdown via `markdown-it`, plus
  plain text/CSV, with in-document search highlighting via `mark.js` and
  inline content editing), and a chat interface with streaming answers,
  inline citations, thumbs up/down feedback, and conversation history

