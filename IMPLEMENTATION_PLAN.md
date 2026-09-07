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
| 1 | **Core Pipeline** | Question → SQL → Result (no clarification, no RAG) | 🔲 Not Started |
| 2 | **RAG Layer** | Schema & knowledge base retrieval | 🔲 Not Started |
| 3 | **Clarification Engine** | Ambiguity detection + follow-up questions | 🔲 Not Started |
| 4 | **Self-Correction & Validation** | SQLGlot validation + retry loops | 🔲 Not Started |
| 5 | **Self-Consistency** *(post-MVP)* | Multi-candidate generation + voting | 🔲 Not Started |
| 6 | **Security & Sandbox** | Read-only execution, blocklist, timeouts | 🔲 Not Started |
| 7 | **Observability** | Langfuse tracing, cost tracking | 🔲 Not Started |
| 8 | **API & Interface** | FastAPI endpoints + UI (Gradio/frontend) | 🔲 Not Started |
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
- [ ] Implement provider-agnostic LLM client (`app/llm/base.py`)
  - Abstract interface: `generate(prompt, system_prompt) -> str`
  - Gemini Flash implementation (`app/llm/gemini.py`)
  - Structured output (JSON with SQL + assumptions)
- [ ] Implement basic SQL generation prompt
  - System prompt with schema (hardcoded for now — RAG comes in Phase 2)
  - User question → SQL output
- [ ] Implement SQLite database execution
  - Connect to demo `data/demo.db`
  - Execute generated SQL
  - Return results as JSON/table
- [ ] Implement result explanation
  - LLM explains what the query returned in plain English
- [ ] Wire it all together as a basic LangGraph graph (linear, no cycles yet)
  - Nodes: generate → execute → explain
- [ ] Basic CLI for testing (`python -m app.cli "What are the top 5 customers?"`)

### Deliverables
- End-to-end: question → SQL → result → explanation
- Works against demo database
- No error handling yet (that's Phase 4)

---

## Phase 2 — RAG Layer

**Goal**: Replace hardcoded schema context with dynamic retrieval from a vector store.

### Tasks
- [ ] Implement schema introspection
  - Connect to SQLite demo DB, read all tables/columns/types/FKs
  - Generate chunked schema documents (one per table)
  - Include sample values for categorical columns
- [ ] Implement knowledge base indexing
  - Read markdown files from `knowledge_base/` directory
  - Chunk and embed them using sentence-transformers (all-MiniLM-L6-v2)
- [ ] Set up ChromaDB (in-process, persistent storage)
  - Create two collections: `schema_chunks` and `business_rules`
  - Implement embedding pipeline using sentence-transformers
- [ ] Implement retrieval
  - Given a user question, retrieve top-K schema chunks + business rules
  - Inject retrieved context into the LLM prompt
- [ ] Write `scripts/index_rag.py` to run the full indexing pipeline
- [ ] Test: verify that retrieval finds the right tables for various questions

### Deliverables
- Schema auto-indexed from SQLite demo database
- Business rules indexed from `knowledge_base/*.md` files
- LLM prompt now uses retrieved context (ChromaDB) instead of hardcoded schema

---

## Phase 3 — Clarification Engine

**Goal**: Detect ambiguous questions and ask the user for clarification before generating SQL.

### Tasks
- [ ] Implement ambiguity detection (Approach A — LLM introspection)
  - Prompt template that asks "is this clear enough to write SQL?"
  - Structured output: `{ is_ambiguous, ambiguity_type, clarification_question, options[] }`
- [ ] Implement clarification state management
  - Track conversation history in LangGraph's AgentState
  - Append clarification Q&A to context for next iteration
  - Limit to 2 clarification rounds max
- [ ] Implement clarification UX
  - Multiple-choice options when possible
  - Open-ended fallback
- [ ] Integrate into LangGraph state machine
  - Add `check_ambiguity` node after RAG retrieval
  - Use LangGraph's `interrupt()` for human-in-the-loop pause
  - On user response → resume pipeline with enriched context
- [ ] (Optional) Implement Approach B — self-consistency disagreement detection
  - Generate N candidates, compare for disagreement
  - Use disagreement points to generate clarification questions

### Deliverables
- System detects ambiguous questions and asks for clarification
- Multi-round clarification dialogue works
- Pipeline pauses/resumes correctly

---

## Phase 4 — Self-Correction & Validation

**Goal**: Catch and fix SQL errors before (and after) hitting the database.

### Tasks
- [ ] Implement SQLGlot validation
  - Parse generated SQL into AST
  - Catch syntax errors
  - Validate against target dialect
- [ ] Implement error feedback loop
  - On parse error → feed error message + original SQL back to LLM
  - LLM regenerates with error context
  - Max 3 validation retries
- [ ] Implement runtime error handling
  - Catch database execution errors (missing column, bad join, etc.)
  - Feed DB error back to LLM for correction
  - Max 3 execution retries
- [ ] Implement security blocklist
  - Traverse AST for DML/DDL nodes
  - Block any query with mutation commands
  - Return user-friendly error message

### Deliverables
- SQL syntax errors caught before DB execution
- Automatic self-correction on validation failures
- Runtime errors trigger retry loop
- No mutation queries can reach the database

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
- [ ] Create read-only PostgreSQL role
  - `CREATE ROLE sqlpilot_readonly LOGIN PASSWORD '...'`
  - `GRANT USAGE ON SCHEMA public TO sqlpilot_readonly`
  - `GRANT SELECT ON ALL TABLES IN SCHEMA public TO sqlpilot_readonly`
- [ ] Configure connection pool with safety limits
  - `statement_timeout = 30000` (30 seconds)
  - `max_rows = 1000` (application-level limit)
  - Connection pool size limits
- [ ] Implement query complexity analysis (optional)
  - Estimate query cost before execution
  - Reject queries that would scan too many rows
- [ ] Rate limiting per user/session

### Deliverables
- Database access is read-only by design
- Queries can't run forever or return unlimited data
- Dangerous operations are blocked at AST level AND DB level (defense in depth)

---

## Phase 7 — Observability

**Goal**: See exactly what the system is doing on every request.

### Tasks
- [ ] Integrate Langfuse Cloud (free tier, 50K observations/month)
  - Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env
  - Wrap each LangGraph node as a Langfuse Span
  - Log RAG retrieval results
  - Log clarification dialogues
  - Log validation attempts and errors
- [ ] Implement cost tracking
  - Track tokens used per request
  - Aggregate daily/weekly cost estimates
- [ ] Implement quality monitoring
  - Log user feedback (thumbs up/down on results)
  - Track self-correction rate (how often does the system retry?)
  - Track clarification trigger rate

### Deliverables
- Full request traces in Langfuse dashboard
- Token/cost tracking
- Quality metrics dashboard

---

## Phase 8 — API & Interface

**Goal**: Expose the pipeline via HTTP API and build a user-facing interface.

### Tasks
- [ ] FastAPI endpoints
  - `POST /query` — submit a question, get SQL + results
  - `POST /clarify` — respond to a clarification question
  - `GET /schema` — view indexed schema
  - `GET /health` — health check
  - WebSocket endpoint for streaming (optional)
- [ ] Pydantic request/response models
- [ ] Error handling and HTTP status codes
- [ ] CORS configuration
- [ ] Build Streamlit chat frontend (`streamlit_app.py`)
  - Chat interface using `st.chat_message` and `st.chat_input`
  - Handle clarification dialogue (show options as buttons)
  - Display SQL, results table, and natural language explanation
  - Show "thinking" spinner during LLM calls
  - Session state management for multi-turn conversations
- [ ] API documentation (auto-generated via FastAPI + manual examples)

### Deliverables
- Working HTTP API
- Interactive UI for asking questions and handling clarification
- API docs

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
