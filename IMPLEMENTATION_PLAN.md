# SQLPilot — Implementation Plan

> Phased roadmap. Each phase builds on the previous one.
> Depends on decisions made in [DESIGN.md](file:///c:/UNIVERSE/Projects/SQLPilot/DESIGN.md).
> Last updated: 2026-09-07
>
> **Finalized Stack**: LangGraph | Gemini Flash | ChromaDB | sentence-transformers | SQLGlot | FastAPI | Streamlit | Langfuse Cloud | Render + Streamlit Cloud

---

## Phase Overview

| Phase | Name | Goal | Status |
|---|---|---|---|
| 0 | **Foundation** | Project structure, configs, dev environment | ✅ Done |
| 1 | **Core Pipeline** | Question → SQL → Result (no clarification, no RAG) | ✅ Done |
| 2 | **RAG Layer** | Schema & knowledge base retrieval | ✅ Done |
| 3 | **Clarification Engine** | Ambiguity detection + follow-up questions | ✅ Done |
| 4 | **Self-Correction & Validation** | SQLGlot validation + retry loops | ✅ Done |
| 5 | **Self-Consistency** *(post-MVP)* | Multi-candidate generation + voting | 🔲 Not Started |
| 6 | **Security & Sandbox** | Read-only execution, blocklist, timeouts | ✅ Done |
| 7 | **Observability** | Langfuse tracing, cost tracking | ✅ Done |
| 8 | **API & Interface** | FastAPI endpoints + UI (Gradio/frontend) | ✅ Done |
| 9 | **Evaluation & Benchmarks** | Internal eval set + benchmark runs | 🔲 Not Started |
| 10 | **Deployment** | Free-tier deployment + Docker Compose | 🔲 Not Started |

---

## Phase 0 — Foundation

**Goal**: Get the project skeleton in place so we can iterate fast.

### Tasks
- [x] Finalize all open decisions in DESIGN.md (sections Q1–Q7)
- [x] Set up project structure (see tree above)
- [x] Set up Python environment (pyproject.toml + requirements.txt)
- [x] Set up .env.example with all required config keys (GEMINI_API_KEY, LANGFUSE_*, DB_URL)
- [x] Create demo SQLite database with the SaaS schema (7 tables)
- [x] Seed demo database with realistic sample data (53 customers, 69 subs, 413 invoices, 75 tickets, 5 products, 1356 usage events, 15 employees)
- [x] Write business rules markdown files in `knowledge_base/` (mrr, churn, revenue, active_users, clv, resolution_time)

### Deliverables
- [x] Working dev environment
- [x] Demo SQLite database with SaaS data at `data/demo.db`
- [x] Business rules knowledge base (6 files)
- [x] CI-ready project structure

---

## Phase 1 — Core Pipeline (Minimal Viable Path)

**Goal**: Take a natural language question, generate SQL, execute it, return results. No RAG, no clarification, no validation — just the happy path.

### Tasks
- [x] Implement provider-agnostic LLM client (`app/llm/base.py`)
  - Abstract interface: `generate(prompt, system_prompt) -> str`
  - Gemini Flash implementation (`app/llm/gemini.py`) — using gemini-3.6-flash
  - Structured output (JSON with SQL + assumptions via `response_mime_type`)
- [x] Implement basic SQL generation prompt
  - System prompt with schema (hardcoded via DB introspection — RAG comes in Phase 2)
  - User question → SQL output
- [x] Implement SQLite database execution
  - Connect to demo `data/demo.db`
  - Execute generated SQL
  - Return results as JSON/table
- [x] Implement result explanation
  - LLM explains what the query returned in plain English
- [x] Wire it all together as a basic LangGraph graph (linear, no cycles yet)
  - Nodes: generate → execute → explain
- [x] Basic CLI for testing (`python -m app.cli "What are the top 5 customers?"`)

### Deliverables
- [x] End-to-end: question → SQL → result → explanation
- [x] Works against demo database (tested with COUNT, multi-table JOIN, GROUP BY)
- No error handling yet (that's Phase 4)

---

## Phase 2 — RAG Layer

**Goal**: Replace hardcoded schema context with dynamic retrieval from a vector store.

### Tasks
- [x] Implement schema introspection (`app/rag/schema_introspector.py`)
  - Connect to SQLite demo DB, read all tables/columns/types/FKs
  - Generate chunked schema documents (one per table)
  - Include sample values for categorical columns (low-cardinality auto-detected)
- [x] Implement knowledge base indexing
  - Read markdown files from `knowledge_base/` directory
  - ChromaDB default embedding (all-MiniLM-L6-v2) handles encoding
- [x] Set up ChromaDB (`app/rag/store.py`, in-process, persistent at `data/chroma/`)
  - Two collections: `schema_chunks` and `business_rules`
  - Full re-index on each run (schema is small, keeps it simple)
- [x] Implement retrieval (`app/rag/retriever.py`)
  - Retrieve top-K schema chunks + business rules
  - Distance-based filtering for rules (< 1.0 cosine distance)
  - Graceful fallback to DB introspection if index is empty
- [x] Write `scripts/index_rag.py` to run the full indexing pipeline
  - Includes sanity check with test queries
- [x] Test: verified retrieval finds right tables + rules for MRR, support tickets, resolution time

### Deliverables
- [x] Schema auto-indexed from SQLite demo database (7 tables)
- [x] Business rules indexed from `knowledge_base/*.md` files (6 rules)
- [x] LLM prompt now uses retrieved context (ChromaDB) instead of hardcoded schema
- [x] Pipeline uses business rules (tested: MRR query correctly follows knowledge base definition)

---

## Phase 3 — Clarification Engine

**Goal**: Detect ambiguous questions and ask the user for clarification before generating SQL.

### Tasks
- [x] Implement ambiguity detection (Approach A -- LLM introspection)
  - Prompt template: `prompts_clarification.py` with 5 ambiguity types
  - Structured output: `{ is_ambiguous, ambiguity_type, confidence, clarification_question, options[], reasoning }`
  - Low-confidence filter (< 0.6) to reduce false positives
- [x] Implement clarification state management (`handle_clarification.py`)
  - Tracks conversation history in AgentState.clarification_history
  - Builds enriched question combining original + clarification response
  - Limit to 2 clarification rounds max, then proceed with best guess
- [x] Implement clarification UX (CLI)
  - Multiple-choice options with number selection
  - Open-ended fallback for free text
  - Skip support (empty input = proceed with best guess)
- [x] Integrate into LangGraph state machine
  - `check_ambiguity` node after RAG retrieval, before generation
  - Graph terminates at `stop_for_clarification` -> caller manages the loop
  - On user response -> handle_clarification -> re-invoke graph
  - Decided against LangGraph interrupt() -- caller-managed loop is simpler
- [x] Added rate limit retry with exponential backoff to Gemini client
- [ ] (Optional) Implement Approach B -- self-consistency disagreement detection
  - Deferred to Phase 5 (self-consistency)

### Deliverables
- [x] System detects ambiguous questions (tested: "Show me revenue" -> metric ambiguity with 4 options)
- [x] Multi-round clarification dialogue works (2 rounds max)
- [x] Pipeline pauses/resumes correctly (graph stops at END, caller re-invokes)
- [x] Clear questions pass through without unnecessary clarification

---

## Phase 4 — Self-Correction & Validation

**Goal**: Catch and fix SQL errors before (and after) hitting the database.

### Tasks
- [x] Implement SQLGlot validation (`app/validation/validator.py`)
  - Three-layer check: keyword blocklist -> syntax parse -> AST mutation scan
  - Dialect-aware parsing (sqlite, postgres, mysql)
  - ValidationResult with error_type, is_recoverable classification
- [x] Implement error feedback loop (`app/agents/nodes/correct_sql.py`)
  - Correction prompts with full error history + schema context (per DESIGN.md §7.4.4)
  - `what_i_changed` field forces LLM to articulate its fix
  - Max 2 validation retries (per DESIGN.md §7.4.1)
- [x] Implement runtime error handling
  - execute_query records errors in correction_history with error classification
  - Recoverable: no such column/table, syntax error, ambiguous column
  - Unrecoverable: permission denied, timeout, connection error
  - Max 2 execution retries
- [x] Implement security blocklist
  - Keyword-level: DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, TRUNCATE, etc.
  - AST-level: walks parse tree for mutation node types (defense in depth)
  - Blocked queries marked unrecoverable -- no retry attempts wasted
  - Tested: "DROP TABLE customers" -> immediate block with clear error
- [x] Updated graph with conditional edges for both correction loops
  - Corrections always re-routed through validate_sql (never skip to execution)
  - explain_with_error terminal node for unrecoverable errors

### Deliverables
- [x] SQL syntax errors caught before DB execution
- [x] Automatic self-correction on validation failures (Loop 1)
- [x] Runtime errors trigger retry loop (Loop 2)
- [x] No mutation queries can reach the database (tested: DROP TABLE blocked)

---

## Phase 5 — Self-Consistency *(Post-MVP Enhancement)*

**Goal**: Improve SQL accuracy by generating multiple candidates and selecting the best one.
**Note**: Skipped for MVP (Decision #3). Add this after the core pipeline is solid and benchmarked.

### Tasks
- [ ] Implement multi-candidate generation
  - Generate N SQL candidates with temperature > 0
  - Configurable N (default: 3)
- [ ] Implement voting mechanism
  - Parse all candidates to AST
  - Group by structural similarity (SQLGlot normalization)
  - Select the most common structure
  - Tie-break: shortest/simplest query
- [ ] Make it configurable
  - Fast mode (N=1, no voting)
  - Accuracy mode (N=3-5, with voting)
  - Config flag: `SELF_CONSISTENCY_ENABLED` + `SELF_CONSISTENCY_N`
- [ ] Benchmark: measure accuracy improvement vs latency cost

### Deliverables
- Multi-candidate generation + voting works
- Configurable via environment variable
- Benchmark numbers: accuracy gain vs latency cost

---

## Phase 6 — Security & Sandbox

**Goal**: Harden the execution environment for production use.

### Tasks
- [x] Enforce read-only execution at database level
  - `PRAGMA query_only = ON` on every connection (SQLite equivalent of read-only role)
  - Writes raise RuntimeError with clear message
  - PostgreSQL roles deferred until Postgres is actually needed
- [x] Statement timeout via `threading.Timer` + `conn.interrupt()`
  - Configurable via `STATEMENT_TIMEOUT_MS` (default 30s)
  - Translates "interrupted" to user-friendly timeout message suggesting query simplification
- [x] Row limit already in place (`fetchmany(max_result_rows)`, default 1000)
- [x] Rate limiting per session (`app/security/rate_limiter.py`)
  - Sliding window counter (in-memory, per-minute)
  - Configurable via `RATE_LIMIT_PER_MINUTE` (default 20)
  - Wired as entry guard node in graph -- rejects before any LLM calls
- [ ] Query complexity analysis (optional, deferred)
  - EXPLAIN QUERY PLAN analysis deferred -- overkill for SQLite demo

### Deliverables
- [x] Database access is read-only by design (tested: DELETE blocked at DB level)
- [x] Queries can't run forever (30s timeout) or return unlimited data (1000 row cap)
- [x] Dangerous operations blocked at three levels: keyword blocklist (Phase 4) + AST walk (Phase 4) + DB-level read-only (Phase 6)
- [x] Rate limiting prevents runaway loops or abuse

---

## Phase 7 — Observability

**Goal**: See exactly what the system is doing on every request.

### Tasks
- [x] Integrate Langfuse Cloud (free tier, 50K observations/month)
  - Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env (LANGFUSE_HOST must match the
    key's region -- these keys are on the `jp` region, not the global default)
  - Wrap each LangGraph node as a Langfuse Span (`app/observability/tracing.py::traced_node`,
    applied to every node in `graph.py`)
  - Log RAG retrieval results, clarification dialogues, validation attempts and errors --
    captured automatically as span input/output since node dict returns already carry this
    state (schema_context, clarification_question/options, validation_error, etc.)
  - One Langfuse trace per user question, spanning every clarification round
    (`start_trace`/`end_trace` in `cli.py`)
- [x] Implement cost tracking
  - Both LLM clients (`GeminiClient`, `GroqClient`) log a Langfuse generation per call with
    prompt/completion/total token counts; Langfuse Cloud computes cost from its model pricing
    table and aggregates it on the dashboard (no custom aggregator needed)
- [x] Implement quality monitoring
  - CLI prompts for thumbs up/down after each answer, logged as a `user_feedback` trace score
  - Self-correction rate (`correction_history` length) and clarification round count logged as
    trace metadata on every run

### Deliverables
- [x] Full request traces in Langfuse dashboard (verified against Langfuse Cloud: node spans,
  nested LLM generations with token usage, multi-round clarification nesting under one trace,
  security-blocklist error path, and user feedback score all confirmed via the Langfuse API)
- [x] Token/cost tracking (token counts confirmed on generations; cost depends on Langfuse
  recognizing the model name in its pricing table)
- [x] Quality metrics dashboard (self-correction attempts + clarification rounds in trace
  metadata, thumbs up/down as trace scores -- all queryable/aggregable in Langfuse Cloud)

---

## Phase 8 — API & Interface

**Goal**: Expose the pipeline via HTTP API and build a user-facing interface.

### Tasks
- [x] FastAPI endpoints (`app/api/routes.py`)
  - `POST /query` — submit a question, get SQL + results, or `clarification_needed`
  - `POST /clarify` — respond to a clarification question (looks up the pending
    state + Langfuse trace by `session_id` in `app/api/session_store.py`, an
    in-memory store bridging the two-request flow -- same tradeoff as the
    rate limiter, fine for a single-process demo, not multi-worker production)
  - `GET /schema` — introspected schema (tables, columns, row counts)
  - `GET /health` — health check
  - WebSocket streaming — skipped (optional per plan)
- [x] Pydantic request/response models (`app/models/schemas.py`)
- [x] Error handling and HTTP status codes -- 422 on invalid input (empty
  question), 404 on an unknown/expired clarification session_id, 500 on
  unexpected pipeline errors (translated from exceptions, e.g. missing DB
  file); business-logic failures (blocked SQL, execution errors) return 200
  with `status: "error"` and a message, same as the CLI
- [x] CORS configuration (permissive `allow_origins=["*"]` -- local/demo API,
  no auth)
- [x] Build Streamlit chat frontend (`streamlit_app.py`) -- talks to the
  FastAPI backend over HTTP (`SQLPILOT_API_URL`, default `localhost:8000`)
  - Chat interface using `st.chat_message` and `st.chat_input`
  - Clarification dialogue shown as buttons (with a free-text fallback)
  - Displays SQL, results table, assumptions, and explanation; errors via `st.error`
  - "Thinking..." spinner during each API call
  - Session state management for multi-turn conversations, plus a
    "New conversation" reset in the sidebar
- [x] API documentation -- FastAPI auto-generates OpenAPI docs at `/docs` and
  `/redoc` from the Pydantic models and endpoint docstrings; request models
  carry a `json_schema_extra` example

### Deliverables
- [x] Working HTTP API (verified live: `/health`, `/schema`, a clear `/query`,
  the `/query` -> `/clarify` two-round ambiguous flow, the security-blocklist
  error path, and both error statuses -- all against the running Groq-backed
  pipeline, not mocked)
- [x] Interactive UI for asking questions and handling clarification (driven
  in an actual browser via Chrome automation: typed a question, got SQL +
  table + explanation; asked an ambiguous question, clicked a clarification
  button, got the follow-up answer -- no console errors)
- [x] API docs (Swagger UI at `/docs`)

---

## Phase 9 — Evaluation & Benchmarks

**Goal**: Quantify how good the system actually is.

### Tasks
- [ ] Create internal eval dataset against our SaaS demo schema
  - 50-100 question/SQL pairs
  - Include ~20 ambiguous questions (should trigger clarification)
  - Include simple, medium, and complex queries
  - Include questions requiring business knowledge
- [ ] Implement evaluation harness
  - Run eval set through the pipeline
  - Compare generated SQL results against gold standard (execution accuracy)
  - Measure clarification precision and recall
  - Measure latency per query
- [ ] (Optional) Run on Spider/BIRD subsets
  - Requires adapter for their schema format
  - Good for bragging rights / README numbers
- [ ] Document results in DESIGN.md

### Deliverables
- Evaluation dataset
- Benchmark results
- Identified weak spots and improvement opportunities

---

## Phase 10 — Deployment

**Goal**: Make it easy for anyone to run SQLPilot.

### Tasks
- [ ] Docker Compose setup
  - All services in one `docker-compose up`
  - Environment variable configuration
- [ ] Free-tier deployment guide
  - Step-by-step for Render (FastAPI backend)
  - Step-by-step for Streamlit Community Cloud (frontend)
  - Include .env setup instructions
- [ ] CI/CD pipeline (GitHub Actions)
  - Run tests on PR
  - Auto-deploy to Render on merge to main
- [ ] Update README.md with:
  - Architecture diagram
  - Quick start guide
  - Benchmark results
  - Screenshots / demo GIF

### Deliverables
- One-command local setup via Docker Compose
- Deployed demo on free tier
- Comprehensive README

---

## Dependencies Between Phases

```
Phase 0 (Foundation)
    │
    ▼
Phase 1 (Core Pipeline) ◄── minimum viable product
    │
    ├──▶ Phase 2 (RAG Layer)
    │        │
    │        ▼
    │    Phase 3 (Clarification Engine)
    │
    ├──▶ Phase 4 (Validation & Self-Correction)
    │        │
    │        ▼
    │    Phase 5 (Self-Consistency) [optional]
    │
    ├──▶ Phase 6 (Security & Sandbox)
    │
    ├──▶ Phase 7 (Observability)
    │
    └──▶ Phase 8 (API & Interface)
              │
              ▼
         Phase 9 (Evaluation)
              │
              ▼
         Phase 10 (Deployment)
```

- Phases 2-7 can be developed somewhat in parallel after Phase 1
- Phase 3 depends on Phase 2 (needs RAG context to detect ambiguity)
- Phase 5 depends on Phase 4 (needs validation to compare candidates)
- Phase 8 can start alongside Phase 2-3 (API structure doesn't depend on internals)
- Phase 9-10 are finalization phases

---

## Estimated Effort

> Rough estimates, will refine as we go.

| Phase | Estimated Time |
|---|---|
| Phase 0 | 1 day |
| Phase 1 | 2-3 days |
| Phase 2 | 2 days |
| Phase 3 | 3-4 days |
| Phase 4 | 2 days |
| Phase 5 | 1-2 days |
| Phase 6 | 1 day |
| Phase 7 | 1-2 days |
| Phase 8 | 2-3 days |
| Phase 9 | 2-3 days |
| Phase 10 | 1-2 days |
| **Total** | **~18-25 days** |
