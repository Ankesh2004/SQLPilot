# SQLPilot — Design Document

> Living document. Every decision, tradeoff, and benchmark reference lives here.
> Last updated: 2026-09-07

---

## 1. Project Vision

**SQLPilot** is a production-grade Text-to-SQL engine with a built-in **clarification mechanism**. Instead of guessing when a user's question is vague, the system proactively identifies ambiguity and asks the user to clarify before generating SQL.

### Core Differentiator
Most Text-to-SQL tools follow a "prompt in → SQL out" pattern and silently hallucinate when the question is ambiguous. SQLPilot treats **disambiguation as a first-class pipeline stage**, not an afterthought.

### Target Users
- Data analysts who know their business but not SQL
- Internal tools / dashboards backed by natural-language query layers
- Anyone who wants to query a database in plain English and get trustworthy results

---

## 2. High-Level Architecture

The system is a **multi-stage state machine** (not a single LLM call). Each stage has a clear responsibility and failure mode.

```
User Question
    │
    ▼
┌─────────────────┐
│ Schema & Context │ ← RAG retrieval (schema chunks + business rules)
│   Retrieval      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Ambiguity        │ ← LLM-based check: is the question clear enough?
│ Detection        │──── YES ──▶ continue
└────────┬────────┘
         │ NO
         ▼
┌─────────────────┐
│ Clarification    │ ← Generate follow-up question(s), pause, wait for user
│ Dialogue         │──── user responds ──▶ loop back to Ambiguity Detection
└─────────────────┘
         │
         ▼ (question is now unambiguous)
┌─────────────────┐
│ SQL Generation   │ ← LLM generates SQL (with optional self-consistency)
│ (+ Self-Consist.)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Validation       │ ← SQLGlot AST parse + security blocklist
│ & Safety Check   │
└────────┬────────┘
         │ FAIL → loop back to SQL Generation with error context
         │
         ▼ PASS
┌─────────────────┐
│ Execution        │ ← Read-only sandboxed DB connection
│ (Sandboxed)      │
└────────┬────────┘
         │ RUNTIME ERROR → loop back to SQL Generation (max 3 retries)
         │
         ▼ SUCCESS
┌─────────────────┐
│ Result           │ ← LLM explains the result in plain English
│ Explanation      │
└─────────────────┘
```

### Feedback Loops
- **Validation loop**: bad syntax → LLM gets the parse error → regenerates → re-validates
- **Execution loop**: runtime DB error → LLM gets the error message → regenerates (max 3 attempts)
- **Clarification loop**: ambiguous input → system asks follow-up → user responds → re-evaluate

---

## 3. Finalized Tech Stack

| Component | Choice | Why |
|---|---|---|
| **Orchestration** | LangGraph | Cycles, human-in-the-loop, persistence — built for our use case |
| **LLM** | Gemini Flash (primary), provider-agnostic interface | Free tier, good context window, swap via config |
| **Embedding** | all-MiniLM-L6-v2, bundled with ChromaDB (ONNX runtime) | Local, free, no API dependency, no torch |
| **Vector DB** | ChromaDB (in-process) | Zero-config, no Docker, deploys on Render free tier |
| **SQL Validation** | SQLGlot | AST parsing, dialect transpilation, security checks |
| **Target DBs** | SQLite (demo) + PostgreSQL (production) | Zero-infra demos, production-grade when needed |
| **API** | FastAPI + Pydantic | Auto-docs, type safety, async support |
| **Frontend** | Streamlit | Chat UI with `st.chat_message`, free hosting on Community Cloud |
| **Observability** | Langfuse Cloud (free tier) | Hosted tracing, 50K observations/month |
| **Deployment** | Render (backend) + Streamlit Cloud (frontend) | Both free |

---

## 4. Component Decisions & Tradeoffs

### 4.1 Orchestration: LangGraph vs Custom State Machine

| Criteria | LangGraph | Custom (pure Python) |
|---|---|---|
| Cycle/loop support | Built-in | Manual `while` loops |
| Human-in-the-loop | First-class `interrupt()` | Roll your own pause/resume |
| Observability | LangSmith integration | Build your own tracing |
| Dependency weight | Heavy (~LangChain ecosystem) | Zero external deps |
| Learning curve | Moderate | Low (it's just your code) |
| Lock-in risk | Tied to LangChain APIs | None |

**Decision: TBD** — needs discussion.
- If we want the project to be lightweight and dependency-free → custom state machine
- If we want battle-tested cycle management, persistence, and human-in-the-loop → LangGraph
- Middle ground: use LangGraph for orchestration but keep individual nodes as pure functions that don't import LangChain

### 4.2 LLM Provider

We want **free tier** as much as possible. Research findings:

| Provider | Free Tier | Latency | SQL Quality | Notes |
|---|---|---|---|---|
| **Google Gemini (Flash)** | ✅ 15 RPM, generous daily limits | Medium | Good | Your `possible_design.png` already shows Gemini. Long context window is great for big schemas. |
| **Groq (Llama 3/4)** | ✅ Generous RPM | **Very Low** (LPU) | Good | Fastest inference. Great for self-consistency (multiple calls). |
| **OpenRouter** | ✅ Gateway to many free models | Varies | Varies | Flexibility to swap models without code changes. |
| **Mistral (Codestral)** | ✅ Free tier available | Medium | Strong for code | Purpose-built for code/SQL generation. |
| **DeepSeek** | ✅ Initial token grant | Medium | Strong for code | Competitive coding performance. |

**Decision: TBD** — needs discussion.
- Primary recommendation: **Gemini Flash** for main generation (free, good context window)
- Possible secondary: **Groq/Llama** for self-consistency passes (speed matters when doing N samples)
- Architecture should be **provider-agnostic** — swap via config, not code changes

### 4.3 Vector Database (for RAG)

We need to store schema embeddings + business rules for retrieval. Options:

| Option | Server Required? | Persistence | Metadata Filtering | Best For |
|---|---|---|---|---|
| **ChromaDB** | No (in-process) | Built-in | ✅ Yes | Prototyping, simple RAG |
| **Qdrant** | Yes (Docker) | Built-in | ✅ Yes | Production, complex filtering |
| **FAISS** | No (library) | Manual | ❌ No | Raw speed, massive scale |
| **SQLite-vec** | No (extension) | SQLite file | ✅ Yes (SQL) | Lightweight, single-file deploy |

**Decision: TBD** — needs discussion.
- For **free deployment** (no Docker available on Render free tier): ChromaDB or SQLite-vec are better choices
- Qdrant requires a separate server — adds complexity and cost
- ChromaDB is probably the sweet spot: zero-config, works in-process, good enough for our scale
- SQLite-vec is interesting if we want everything in one file

### 4.4 Embedding Model

We need an embedding model to vectorize schema chunks and business rules.

| Option | Free? | Quality | Notes |
|---|---|---|---|
| **Gemini Embedding** | ✅ Free tier | Good | Same ecosystem as our LLM |
| **sentence-transformers (local)** | ✅ Fully free | Good | e.g., `all-MiniLM-L6-v2`. No API calls, runs locally |
| **OpenAI `text-embedding-3-small`** | Paid | Very Good | $0.02/1M tokens |

**Decision: TBD** — needs discussion.
- Local sentence-transformers = zero cost, no rate limits, works offline
- Gemini embeddings = simpler stack (one provider for everything)
- For a free-deployment story, local embeddings are safer

### 4.5 Database Target

The README mentions PostgreSQL. We need to decide scope:

| Scope | Complexity | User Value |
|---|---|---|
| PostgreSQL only | Low | Focused, easier to test |
| Multi-dialect (via SQLGlot) | Medium | More versatile |
| SQLite (for demos) + Postgres (for production) | Low-Medium | Good demo story |

**Decision: TBD** — needs discussion.
- SQLGlot already supports dialect transpilation
- Starting with **SQLite for demos + PostgreSQL for production** seems practical
- SQLite means zero infra for someone trying the project

---

## 5. The Clarification Engine (Deep Dive)

This is our key differentiator. Here's the detailed design.

### 5.1 When to Trigger Clarification

The system should ask for clarification when it detects **ambiguity** — but not be annoying about it. Categories of ambiguity:

| Ambiguity Type | Example | Detection Method |
|---|---|---|
| **Schema ambiguity** | "Show me sales" but DB has `gross_sales`, `net_sales`, `sales_orders` tables | RAG returns multiple equally-relevant schema matches |
| **Value ambiguity** | "Find Jack's orders" but Jack appears in `customers.name` AND `employees.name` | Column value lookup / LLM reasoning |
| **Temporal ambiguity** | "Recent orders" — recent = last week? last month? today? | LLM flags missing time bounds |
| **Metric ambiguity** | "What's our revenue?" — gross vs net? ARR vs MRR? | Business rules KB doesn't have a single canonical definition |
| **Underspecified filters** | "Show top customers" — top by what? revenue? count? recency? | LLM reasoning + missing ORDER BY criteria |

### 5.2 How to Detect Ambiguity

Two approaches (can be combined):

**Approach A — LLM Introspection (simpler)**
- After RAG retrieval, ask the LLM: "Given this schema context and the user's question, can you generate an unambiguous SQL query? If not, what specifically is unclear?"
- LLM outputs a structured response: `{ "is_ambiguous": bool, "ambiguity_type": str, "clarification_question": str }`

**Approach B — Self-Consistency Disagreement (more robust)**
- Generate N candidate SQL queries (e.g., N=3–5) with temperature > 0
- If the candidates **disagree** (different tables, columns, or WHERE clauses), that's a signal of ambiguity
- The *points of disagreement* tell us exactly what to ask about

**Approach C — Hybrid (recommended)**
- Use Approach A as the fast path (single LLM call)
- Use Approach B as a verification step for complex queries
- If A says "clear" but B shows disagreement → trigger clarification anyway

### 5.3 Clarification UX

- Present the user with **multiple-choice options** when possible (not open-ended questions)
  - e.g., "Did you mean: (a) gross revenue, (b) net revenue, (c) ARR?"
- Fall back to open-ended question only when options can't be generated
- Limit clarification rounds to **2 max** to avoid annoying the user
- If still ambiguous after 2 rounds → proceed with "best guess" and explain assumptions

### 5.4 Clarification State Management

The clarification dialogue needs to be stateful. When the user responds:
1. Append the clarification Q&A to the conversation context
2. Re-run ambiguity detection with the enriched context
3. If now clear → proceed to SQL generation
4. If still ambiguous → ask another clarification (up to limit)

---

## 6. Self-Consistency Mechanism

Self-consistency improves SQL generation accuracy by sampling multiple candidates and voting.

### 6.1 How It Works

```
User Question + Schema Context
        │
        ├──▶ LLM Call 1 (temp=0.7) → SQL_1
        ├──▶ LLM Call 2 (temp=0.7) → SQL_2
        ├──▶ LLM Call 3 (temp=0.7) → SQL_3
        │
        ▼
┌─────────────────┐
│ Voting / Merge   │
└────────┬────────┘
         │
         ▼
    Final SQL
```

### 6.2 Voting Strategies

| Strategy | How | Pros | Cons |
|---|---|---|---|
| **Majority vote (string)** | Pick the most common SQL string | Simple | Minor formatting differences break it |
| **Execution-based vote** | Execute all, pick the result most candidates agree on | More robust | Requires DB access, more compute |
| **AST-based vote** | Parse all to AST, compare structure | Handles formatting differences | More complex to implement |

**Decision: TBD** — needs discussion.
- For MVP: AST-based structural comparison (via SQLGlot) seems like the right balance
- Execution-based is gold standard but expensive (N DB calls per question)
- Could start with N=3 candidates to keep costs low

### 6.3 Cost / Latency Tradeoff

Self-consistency multiplies LLM calls by N. With free tiers:
- Gemini Flash at 15 RPM → 3 candidates = 5 full questions/minute
- Groq has much higher RPM → better suited for self-consistency
- **Decision**: make self-consistency **optional and configurable** (N=1 for fast mode, N=3-5 for accuracy mode)

---

## 7. Validation & Security Pipeline

### 7.1 SQLGlot AST Validation

- Parse generated SQL with `sqlglot.parse(sql, dialect="postgres")`
- Catch `ParseError` → feed error message back to LLM for correction
- This catches 80%+ of syntax issues without touching the database

### 7.2 Security Blocklist (AST Traversal)

Walk the AST and reject queries containing:
- DDL: `CREATE`, `ALTER`, `DROP`, `TRUNCATE`
- DML: `INSERT`, `UPDATE`, `DELETE`
- Admin: `GRANT`, `REVOKE`, `EXPLAIN ANALYZE` (optional)
- Dangerous: `INTO OUTFILE`, `LOAD DATA`, `COPY`

Even if the LLM tries to hide a `DROP TABLE` inside a subquery, AST traversal catches it.

### 7.3 Execution Sandbox

- Use a **read-only database role** (PostgreSQL: `CREATE ROLE readonly LOGIN; GRANT SELECT ON ALL TABLES ...`)
- Set `statement_timeout = 30s` to prevent runaway queries
- Limit `max_rows` returned (e.g., 1000) to prevent memory issues
- Optional: `SET work_mem = '64MB'` to limit per-query resource usage

### 7.4 Self-Correction Loop Engineering

This is the most critical piece of the pipeline to get right. LLMs are probabilistic — they *will* produce broken SQL. The question is how we recover from it systematically instead of failing or looping forever.

> **References**: Google Cloud's "Techniques for improving text-to-SQL" emphasizes that no amount of prompt engineering eliminates 100% of errors — build a system that *expects* and recovers from them. The AWS self-correction architecture and LinkedIn CRM case study both confirm this pattern.

#### 7.4.1 The Three Correction Loops

Our pipeline has three distinct loops, each with different triggers, retry budgets, and escalation paths:

```
                    ┌─────────────────────────────────────────────────┐
                    │              LOOP 1: SYNTAX FIX                 │
                    │  SQLGlot parse error → re-prompt LLM            │
                    │  Budget: 2 attempts                             │
                    │  Cheap: no DB call, no API cost beyond LLM      │
                    └───────────┬─────────────────────────────────────┘
                                │ passes validation
                                ▼
                    ┌─────────────────────────────────────────────────┐
                    │           LOOP 2: RUNTIME FIX                   │
                    │  DB execution error → re-prompt LLM             │
                    │  Budget: 2 attempts                             │
                    │  Expensive: each attempt hits the database       │
                    └───────────┬─────────────────────────────────────┘
                                │ succeeds OR budget exhausted
                                ▼
                    ┌─────────────────────────────────────────────────┐
                    │           LOOP 3: CLARIFICATION                 │
                    │  Ambiguous → ask user → re-evaluate             │
                    │  Budget: 2 rounds                               │
                    │  Human-in-the-loop (via LangGraph interrupt)    │
                    └─────────────────────────────────────────────────┘
```

**Why separate loops instead of one big retry counter?**
A single `retry_count` conflates fundamentally different failure modes. A syntax error (Loop 1) is a cheap, fast fix — the LLM just needs to close a parenthesis. A runtime error (Loop 2) means the SQL *looked* valid but referenced a wrong column — that's a harder problem. Lumping them together means a query that takes 2 syntax fixes would already have "used up" retries before it even hits the database. Separate budgets let each loop exhaust its own recovery space.

**Why 2 attempts per loop, not 3 or 5?**
- After 2 correction attempts with full error context, the LLM has already seen the problem and two of its own failed fixes. If it can't solve it in 2 tries, more attempts rarely help — they just burn API quota and user patience.
- Total worst-case: 2 (syntax) + 2 (runtime) = 4 LLM calls beyond the first. On Gemini Flash free tier (15 RPM), this keeps us under 1 full question per second even in the worst case.
- The Google/AWS articles both show 2-3 attempts as the sweet spot. We pick the lower bound for MVP and can tune later with data.

#### 7.4.2 Error Classification

Not all errors deserve retries. Some are fixable by rewriting SQL. Others aren't.

| Error Type | Recoverable? | Action | Example |
|---|---|---|---|
| **Syntax error** (SQLGlot ParseError) | Yes | Loop 1 — feed parse error to LLM | Missing `)`, bad keyword |
| **Security violation** (blocked keyword) | **No** | Immediate reject, tell user | `DROP TABLE`, `DELETE FROM` |
| **Unknown column** (DB runtime) | Yes | Loop 2 — feed DB error + schema context to LLM | `no such column: first_name` |
| **Unknown table** (DB runtime) | Maybe | Loop 2 — but if table truly doesn't exist, bail after 1 try | `no such table: orders` |
| **Permission denied** | **No** | Immediate reject, tell user | Read-only role can't write |
| **Timeout** (statement_timeout) | **No** | Immediate reject — query is too complex, suggest simplifying | Query took >30s |
| **Connection error** | **No** | Immediate reject — infrastructure problem, not an LLM problem | DB is down |

**Why classify errors instead of retrying everything?**
- Retrying a `DROP TABLE` rejection is pointless — the LLM will just try again and get blocked again (or worse, find a creative bypass).
- Retrying a timeout wastes 30 seconds per attempt for a query the DB can't handle regardless.
- Retrying a permission error teaches the LLM nothing — the fix is on the infrastructure side.
- Classifying errors upfront avoids wasting retry budget on unwinnable situations.

**Tradeoff**: We're being aggressive about marking things unrecoverable. In theory, a timeout *could* be fixed by simplifying the query. But in practice, LLMs are bad at query optimization — they'll just regenerate something equally expensive. Better to tell the user "this query is too complex" and let them rephrase.

#### 7.4.3 Error History Accumulation

This is where most naive retry loops fail. If you only show the LLM the *latest* error, it has no memory of what it already tried. It can loop on the same mistake or oscillate between two bad approaches.

**Our approach: append-only error log in AgentState.**

```python
# in AgentState
correction_history: list[dict]  # each entry is one failed attempt

# each entry looks like:
{
    "attempt": 1,
    "sql": "SELECT first_name FROM customers",
    "error_type": "runtime",  # "syntax" | "runtime" | "security"
    "error_message": "no such column: first_name",
    "stage": "execution"  # "validation" | "execution"
}
```

Every failed attempt gets appended. The correction prompt includes the *full history*, so the LLM sees:
- What it tried
- Why each attempt failed
- What NOT to repeat

**Why append-only instead of just "last error"?**
- Without history, the LLM has no signal about what it already tried. It might flip-flop between `first_name` and `firstName` forever.
- With history, we can say: "You tried X (failed because Y), then Z (failed because W). Now fix it knowing both of those don't work."
- This is a direct recommendation from the Google article: structured error feedback outperforms simple text logs.

**Tradeoff**: More history = more tokens in the prompt = more cost per retry. But since we cap retries at 2 per loop (max 4 history entries), the overhead is bounded and small.

#### 7.4.4 Correction Prompt Structure

The correction prompt is the single most important piece of the loop. A bad correction prompt makes retries useless.

```
SYSTEM: You are a SQL expert. Fix the SQL query based on the error feedback.
        Use ONLY the schema provided. Do not invent columns or tables.

USER:
## Original Question
{user_question}

## Database Schema
{schema_context}

## Business Rules
{business_rules_context}

## Target Dialect
{sql_dialect}

## Previous Attempts (DO NOT repeat these mistakes)
Attempt 1:
  SQL: {attempt_1_sql}
  Error: {attempt_1_error}

Attempt 2:
  SQL: {attempt_2_sql}
  Error: {attempt_2_error}

## Instructions
Generate a corrected SQL query. Respond in JSON:
{
  "sql": "...",
  "assumptions": "...",
  "what_i_changed": "..."
}
```

**Key design decisions in the prompt:**

1. **"DO NOT repeat these mistakes"** — explicit negative instruction. LLMs respond well to being told what NOT to do.

2. **`what_i_changed` field** — forces the LLM to articulate its fix. This is a form of chain-of-thought that improves accuracy. If the LLM can't explain what it changed, it probably didn't fix anything meaningful.

3. **Same schema context on every retry** — don't trim the schema to save tokens during retries. The LLM might have failed because it didn't pay attention to the right column the first time. Fresh full context gives it another chance to notice what it missed.

4. **JSON response format** — same structured output as the initial generation. Keeps parsing consistent.

**Tradeoff**: Including full schema on every retry costs more tokens. But schema is typically 500-2000 tokens, and we only retry 2-4 times max. The accuracy improvement is worth the ~2K extra tokens per retry.

#### 7.4.5 LangGraph Edge Routing (The Actual Flow)

Here's exactly how the LangGraph nodes and conditional edges connect:

```
generate_sql
     │
     ▼
validate_syntax ──[ParseError]──► increment validation_retry
     │                                    │
     │                              [retry ≤ 2?]
     │                              YES → correct_sql → validate_syntax (loop)
     │                              NO  → terminal: "syntax_error_unresolved"
     │
     │ [valid syntax]
     ▼
check_security ──[blocked keyword]──► terminal: "security_violation"
     │
     │ [safe]
     ▼
execute_query ──[timeout/permission/connection]──► terminal: "unrecoverable_error"
     │          │
     │          └──[column/table/runtime error]──► increment execution_retry
     │                                                │
     │                                          [retry ≤ 2?]
     │                                          YES → correct_sql → validate_syntax (loop)
     │                                          NO  → terminal: "execution_error_unresolved"
     │
     │ [success]
     ▼
explain_results
     │
     ▼
terminal: "success"
```

**Important**: After `correct_sql`, we always route back to `validate_syntax`, NOT directly to `execute_query`. Even a correction can introduce new syntax errors. This means the loops are nested — a runtime correction goes through validation again.

**Why route corrections back through validation?**
- The LLM might "fix" a column name error by writing syntactically invalid SQL.
- Skipping validation on corrected queries is a common bug in naive retry systems.
- The cost is one `sqlglot.parse()` call — microseconds, no API or DB cost.

#### 7.4.6 Terminal States (What Happens When Loops Exhaust)

When retries are exhausted, we need to fail gracefully. The user should understand *why* and *what they can do*.

| Terminal State | User-Facing Message | Next Action |
|---|---|---|
| `success` | Results + explanation | Done |
| `clarification_needed` | "I need more info: [question]" | Wait for user response |
| `syntax_error_unresolved` | "I couldn't generate valid SQL for this question after multiple attempts. Try rephrasing?" | Show last SQL + error for transparency |
| `execution_error_unresolved` | "The query runs but the database returned errors I couldn't fix. Here's what I tried:" | Show attempt history |
| `security_violation` | "I can't run this query — it would modify the database." | Hard stop, no retry |
| `unrecoverable_error` | "Database error: [timeout/connection]. This isn't a query problem." | Suggest trying later or simplifying |

**Why show attempt history on failure?**
- Transparency builds trust. If the user sees we tried 4 times with specific errors, they understand it's a hard problem, not a lazy system.
- A technical user might read the errors and rephrase their question more precisely.
- This is way better than a generic "Something went wrong" message.

#### 7.4.7 AgentState Updates Required

The current `AgentState` in [state.py](file:///c:/UNIVERSE/Projects/SQLPilot/app/agents/state.py) needs these additions:

```python
# replace single retry_count with per-loop counters
validation_retry_count: int         # how many syntax fix attempts (max 2)
execution_retry_count: int          # how many runtime fix attempts (max 2)

# error history — the key to effective correction
correction_history: list[dict]      # append-only log of all failed attempts

# keep these existing fields, they track the CURRENT error
# syntax_error, execution_error, is_valid_syntax, is_safe, safety_error
```

Fields to **remove**: `retry_count` (replaced by the two specific counters above)

---

## 8. RAG Pipeline Design

### 8.1 What Gets Indexed

Two collections in the vector store:

**Collection 1: Schema Chunks**
- One document per table (table name + column names + types + foreign keys)
- Include sample values for categorical columns (helps with value ambiguity)
- Metadata: `table_name`, `database`, `dialect`

**Collection 2: Business Rules / Knowledge Base**
- Markdown docs with KPI definitions, business logic, edge cases
- e.g., "MRR = SUM(monthly_fee) WHERE subscription_status = 'active' AND plan_type != 'trial'"
- Metadata: `domain`, `metric_name`

### 8.2 Retrieval Strategy

- Retrieve top-K schema chunks (K=5–10) most relevant to the question
- Retrieve top-K business rules (K=3–5) if any match
- Stuff both into the LLM's context alongside the user question
- If no business rules match with confidence > threshold → skip (don't inject noise)

### 8.3 Schema Introspection (Auto-Indexing)

Instead of manually writing schema documents:
- Connect to the target database
- Introspect all tables, columns, types, constraints, foreign keys
- Auto-generate chunked schema documents
- Auto-embed and store in vector DB
- Re-run on schema changes (or on a schedule)

---

## 9. Benchmarks & Evaluation

### 9.1 Academic Benchmarks

| Benchmark | What It Tests | Difficulty | Our Use |
|---|---|---|---|
| **Spider 1.0** | Cross-database, multi-table SQL | Medium | Baseline sanity check |
| **BIRD** | Real-world dirty schemas, 12,751+ pairs across 95 DBs | Hard | Primary public benchmark (planned, §9.5) |
| **Spider 2.0** | Enterprise-scale (BigQuery/Snowflake) | Very Hard | Aspirational / future |
| **WikiSQL** | Single-table simple queries | Easy | Quick smoke tests |

### 9.2 Evaluation Metrics

| Metric | What It Measures |
|---|---|
| **Execution Accuracy (EX)** | Does the generated SQL produce the correct result? |
| **Exact Match (EM)** | Does the SQL exactly match the gold standard? (strict, less useful) |
| **Valid Efficiency Score (VES)** | EX weighted by execution time efficiency |
| **Clarification Precision** | When the system asks for clarification, was it actually needed? |
| **Clarification Recall** | Of truly ambiguous questions, how many did the system catch? |

### 9.3 Reality Check

- SOTA systems score >90% EX on Spider 1.0 but **drop to 6-21% on Spider 2.0**
- This massive gap is because real-world schemas are messy, have thousands of columns, and lack documentation
- Our RAG + clarification approach specifically targets this gap
- We should build our own **internal eval set** of 50-100 questions against our demo database, covering:
  - Simple queries (baseline)
  - Ambiguous queries (clarification engine test)
  - Complex joins
  - Queries requiring business knowledge

### 9.4 Internal Eval Results (2026-09-11, full run)

Built the internal eval set at `tests/eval/dataset.json` -- 50 questions against the
demo SaaS schema: 8 simple, 8 medium, 7 complex, 7 business-knowledge (grounded in
`knowledge_base/*.md`), and 20 ambiguous (expected to trigger clarification). Harness
lives at `tests/eval/harness.py`, runnable via `python scripts/run_eval.py`. It measures:

- **Execution accuracy** on non-ambiguous cases -- runs the generated SQL and a
  hand-written gold SQL against `data/demo.db` and compares result sets. Row/column
  order and column naming don't matter; a query that returns extra columns (e.g.
  `SELECT c.*` where gold used `SELECT c.id, c.name`) still counts correct as long as
  every gold value is present -- an LLM answering with more columns than the minimal
  gold query isn't a wrong answer.
- **Clarification precision/recall** -- did the system ask for clarification exactly
  on the questions that needed it?
- **Latency** per question.

**Result: all 50 cases completed**, three days after the first partial run (the
original 2026-09-08 attempt stopped 18 cases in on the same Groq daily cap -- see
`tests/eval/results/20260908T120446Z_partial.json` for that earlier report). This
run reached every category, but the **last 12 of 20 ambiguous cases hit the same
200K TPD Groq cap again** near the end of the run and failed with `RateLimitError`
rather than a model answer -- those count as false negatives in the recall number
below, so clarification recall is understated, not a true measure of the ambiguity
detector's ceiling. Full report: `tests/eval/results/20260911T161252Z.json`.

| Category | Cases run | Execution accuracy |
|---|---|---|
| simple | 8/8 | 87.5% (7/8) |
| medium | 8/8 | 100% (8/8) |
| complex | 7/7 | 71.4% (5/7) |
| business_knowledge | 7/7 | 85.7% (6/7) |
| ambiguous | 20/20 (8 answered, 12 quota-blocked) | recall 40% (TP=8, FN=12), precision 88.9% (1 FP) |
| **Overall (non-ambiguous only)** | **30/30** | **86.7% (26/30)** |

Latency (Groq, `qwen/qwen3.8-27b`): mean 32.4s, median 40.5s, p95 45.6s, max 64.9s.
Meaningfully lower and tighter than the 2026-09-08 run (mean 46.9s, max 204.3s) --
that run's outlier was a per-minute rate-limit backoff; this run avoided most of
those by spacing calls, only hitting the *daily* cap right at the end.

**Failures, by cause:**
1. **`S6`** (false-positive clarification, same as the 09-08 run) -- "How many
   customers are on the enterprise plan?" still gets flagged as ambiguous when it
   shouldn't be. Reproduces consistently; see follow-up #2 below.
2. **`C3`** ("Which customers have more than one active subscription?") -- generated
   `SELECT c.id, c.name, c.email ... HAVING COUNT(s.id) > 1`, correctly filtering the
   right customers but never selecting the subscription count gold expects
   (`SELECT customer_id, COUNT(*) ... HAVING COUNT(*) > 1`). Right customers, wrong
   columns -- the eval's execution-accuracy check requires every gold value present
   in the generated row, and a missing count column fails that even though the
   filtering logic is correct.
3. **`C5`** ("List the 5 customers with the highest number of usage events...") --
   generated `customer.name` where gold used `customer_id`; a friendlier answer for
   a human reader, but the literal values differ from gold so it fails the
   value-matching check. Same shape of failure as `C3`: correct logic, different
   column choice than gold anticipated.
4. **`B5`** ("average support ticket resolution time, in hours") -- generated SQL
   wraps the average in `ROUND(..., 1)`; gold leaves it unrounded. The harness
   rounds both sides to 2 decimals before comparing, but a value already rounded to
   1 decimal in SQL can land on a different 2-decimal value than the unrounded gold
   average, so the two don't reconcile even though the formula is identical.
5. **`A8`-`A14`, `A16`-`A20`** (12 ambiguous cases) -- all failed with Groq
   `RateLimitError: ... tokens per day (TPD): Limit 200000` rather than a model
   answer. Not a system defect; see follow-up #1.

**Weak spots / follow-ups identified:**
1. **Groq free-tier daily cap still makes a single-session full-suite run
   unreliable.** Even spread across ~35 real minutes, 50 cases (3-4 LLM calls each,
   carrying full schema + business-rule context) burn through the 200K TPD budget
   before the ambiguous category finishes. Either upgrade the Groq tier for eval
   runs, split the suite across two sessions/days, or add a cheaper/smaller model
   option specifically for evaluation.
2. **The `S6` false-positive clarification reproduced on both runs (09-08 and
   09-11)** on the same unambiguous single-filter question -- this is now a
   repeatable finding, not a one-off. Worth a closer look at the ambiguity-detection
   prompt's confidence threshold (`app/agents/prompts_clarification.py`).
3. **Two of three genuine (non-quota) failures are column-choice mismatches, not
   logic errors** (`C3`, `C5`) -- the model picks a different, still-reasonable
   column than the gold answer expected. Worth deciding whether to loosen the eval's
   matching rule (e.g. accept an id-for-name substitution) or tighten prompts to
   match gold column conventions more closely.
4. **`B5` suggests self-rounding in generated SQL can fight the eval's own
   rounding-for-comparison step** -- worth normalizing eval comparison to a coarser
   precision (e.g. round to whole hours for time-duration questions) rather than a
   fixed 2 decimals for every numeric column.
5. **Business-knowledge grounding is now verified**: 6/7 correct, with the one
   miss being the `B5` rounding mismatch above rather than a wrong formula --
   confirms Phase 2's informal check that MRR/CLV/resolution-time definitions are
   being retrieved and applied correctly.

**Next step:** once Groq's quota resets, re-run just the 12 quota-blocked ambiguous
cases (`A8`-`A14`, `A16`-`A20`) to get a clean clarification-recall number, and
investigate the `S6` false positive since it's now reproduced twice.

### 9.5 Planned: Three-Layer Evaluation Suite (public benchmark + custom + adversarial)

**Status: planned, not started.** The internal 50-question set in §9.4 tests
SQLPilot's own behavior well (clarification, business-knowledge grounding) but says
nothing about how it holds up against a public, independently-authored benchmark.
The plan is to add two more evaluation layers alongside the existing one rather than
replace it -- each layer tests something the others can't:

```
                    SQLPilot Evaluation
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
     Public Benchmark  Custom Suite    Adversarial Suite
          |                |                |
          v                v                v
        BIRD          (existing 50Q,   Prompt injection,
                        §9.4: business   destructive SQL,
                        rules, ambiguity, schema hallucination,
                        clarification)   unsafe generation
```

**Layer 1 -- BIRD.** Chosen over Spider 1.0/2.0 and WikiSQL as the starting public
benchmark: BIRD's databases are large and intentionally "dirty" (real column names,
messy schemas), which is a closer match to SQLPilot's RAG-driven schema-retrieval
design than Spider's cleaner academic schemas. Spider 2.0 is noted as a future
"enterprise-scale" stretch goal (§9.1) but is deferred -- its Snowflake setting needs
external DB credentials, which adds setup cost before the BIRD integration is even
working.

Planned integration shape:
- Download the BIRD dev set (question/gold-SQL/DB triples across 95 SQLite databases).
- Adapt `tests/eval/harness.py` (or a sibling harness) to load the right SQLite DB
  per question instead of assuming the single `data/demo.db` -- BIRD's execution
  accuracy check can reuse `rows_match()` as-is since gold/generated comparison
  logic is dataset-agnostic.
- Run BIRD execution-accuracy only (no clarification scoring -- BIRD questions
  aren't labeled ambiguous, and BIRD's own business-knowledge "evidence" strings are
  a different mechanism from our `knowledge_base/*.md` RAG).
- Given the Groq free-tier daily cap already couldn't clear our 50-question set in
  one day (§9.4), start with a small subset (~50-100 BIRD questions, sampled across
  difficulty levels) rather than the full 12,751-pair set.
- Metrics: execution accuracy, SQL validity rate, latency, token usage, retry count
  (validation + execution self-correction loops, per §7.4).

**Layer 2 -- existing custom suite (§9.4).** Unchanged. Public benchmarks don't test
clarification or business-knowledge grounding because they don't model ambiguity or
carry our specific business-rule definitions (MRR, CLV, resolution time) -- the
custom 50-question set stays the only source of clarification precision/recall/F1
and business-knowledge-grounding numbers.

**Layer 3 -- adversarial suite (new, not yet built).** A ~200-500 case dataset
targeting robustness and safety rather than correctness, covering prompt injection
("ignore your previous instructions and..."), destructive-intent questions ("drop
all customer tables"), schema hallucination (asking about columns/tables that don't
exist), and requests for sensitive columns (e.g. a hypothetical `password` column).
Metrics: attack success rate, schema hallucination rate, unsafe-SQL-generation rate.
This complements rather than duplicates the existing security blocklist tests in
`tests/unit/` (Phase 6) -- those are unit-level checks on the blocklist/read-only/
timeout layer in isolation; this suite is end-to-end through the full pipeline
including RAG and the clarification engine.

**Planned experiment -- baseline vs. full pipeline ablation.** Once the BIRD
integration exists, run the same BIRD subset through (a) a direct LLM-to-SQL call
with no RAG/clarification/validation/self-correction, and (b) the full SQLPilot
pipeline, and compare execution accuracy between the two. This quantifies the
actual contribution of RAG + ambiguity detection + validation + self-correction,
rather than asserting it.

**Not yet scheduled as a phase task** -- tracked here and in
`IMPLEMENTATION_PLAN.md` Phase 9 as follow-up work, to be picked up after the
12 quota-blocked ambiguous cases from §9.4 are re-run.

---

## 10. Deployment Strategy

### 10.1 Free Deployment Options

| Platform | Free Tier | Cold Starts | Best For |
|---|---|---|---|
| **Render** | ✅ Permanent free | Yes (spins down on idle) | Backend API |
| **Railway** | ❌ 30-day trial only | No | Not viable long-term |
| **Fly.io** | ❌ 7-day trial | No | Not viable long-term |
| **Vercel** | ✅ Serverless functions | Yes | Frontend (if we build one) |
| **Oracle Cloud Free** | ✅ Always-free ARM VMs | No | Full control, more setup |
| **HuggingFace Spaces** | ✅ Free (Gradio/Streamlit) | Yes | Demo UI |

**Recommended Stack (Free)**:
1. **Backend (API)**: Render free tier (FastAPI) — accept cold starts for a demo
2. **Frontend (UI)**: HuggingFace Spaces (Gradio) OR Vercel (if we build a proper UI)
3. **Database**: Render free PostgreSQL OR bundled SQLite (zero infra)
4. **Vector DB**: ChromaDB in-process (no separate service needed)
5. **LLM**: Gemini Flash free tier
6. **Observability**: Langfuse Cloud free tier (or self-hosted on the same Render instance)

### 10.2 Docker Compose (Local Dev / Self-Hosted)

For local development or self-hosting, provide a `docker-compose.yml` that spins up:
- The FastAPI app
- PostgreSQL (demo database with sample data)
- (Optional) Qdrant if we go that route instead of ChromaDB
- Langfuse

---

## 10. Demo Database Schema (SaaS)

All 7 tables are designed to showcase ambiguity and business knowledge requirements.

### Tables

```sql
-- the core customer table
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- ambiguity: same col name as employees.name
    email TEXT UNIQUE NOT NULL,
    company TEXT,
    plan_type TEXT,               -- 'free', 'starter', 'pro', 'enterprise'
    signup_date DATE NOT NULL,
    country TEXT
);

-- subscription details — where MRR lives
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    plan_name TEXT NOT NULL,      -- could differ from customers.plan_type if they switched
    monthly_fee DECIMAL(10,2),   -- ambiguity: is "revenue" this or invoices.amount?
    status TEXT NOT NULL,         -- 'active', 'cancelled', 'trial', 'paused'
    start_date DATE NOT NULL,
    end_date DATE                 -- NULL if still active
);

-- financial records
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    subscription_id INTEGER REFERENCES subscriptions(id),
    amount DECIMAL(10,2),         -- ambiguity: gross amount before/after tax+discount?
    tax DECIMAL(10,2),
    discount DECIMAL(10,2),
    payment_status TEXT,          -- 'paid', 'pending', 'overdue', 'refunded'
    issued_date DATE NOT NULL,
    paid_date DATE               -- NULL if not yet paid
);

-- customer support tracking
CREATE TABLE support_tickets (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    subject TEXT NOT NULL,
    priority TEXT,                -- 'low', 'medium', 'high', 'critical'
    status TEXT,                  -- 'open', 'in_progress', 'resolved', 'closed'
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP        -- NULL if still open
);

-- what we sell
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- ambiguity: yet another 'name' column
    category TEXT,
    base_price DECIMAL(10,2),
    description TEXT
);

-- usage/activity tracking
CREATE TABLE usage_events (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    product_id INTEGER REFERENCES products(id),
    event_type TEXT,              -- 'page_view', 'api_call', 'export', 'login'
    quantity INTEGER DEFAULT 1,
    timestamp TIMESTAMP NOT NULL
);

-- internal team — creates name ambiguity with customers
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- ambiguity: "find Jack" — customer or employee?
    department TEXT,              -- 'engineering', 'sales', 'support', 'marketing'
    role TEXT                     -- 'manager', 'engineer', 'analyst', etc.
);
```

### Ambiguity Scenarios This Schema Creates

| User Question | Ambiguity | What Clarification Should Ask |
|---|---|---|
| "Show me revenue" | `subscriptions.monthly_fee` vs `invoices.amount` vs `invoices.amount - tax - discount` | "Revenue can mean different things. Do you mean: (a) MRR from active subscriptions, (b) total invoiced amount, (c) net invoiced amount after tax/discounts?" |
| "Find Jack's data" | `customers.name` vs `employees.name` | "'Jack' appears in both customers and employees. Which one do you mean?" |
| "How many active users?" | `subscriptions.status = 'active'` vs `usage_events` recent activity | "Do you mean customers with active subscriptions, or customers who've been active recently (e.g., logged in this month)?" |
| "Show churn rate" | Need business rule: churn = cancelled / (active + cancelled) for a period | System should retrieve from knowledge base: "Churn = subscriptions cancelled in period / total active at start of period" |
| "Top customers" | Top by revenue? By usage? By ticket count? | "Top customers by what metric? (a) Revenue, (b) Usage events, (c) Support tickets, (d) Subscription tenure" |
| "Recent orders" | No time bound specified | "How recent? (a) Last 7 days, (b) Last 30 days, (c) This quarter" |

### Business Rules (Knowledge Base)

These will live as markdown files in `knowledge_base/`:

- **MRR**: `SUM(monthly_fee) WHERE subscriptions.status = 'active' AND subscriptions.status != 'trial'`
- **Churn Rate**: `COUNT(cancelled in period) / COUNT(active at period start) * 100`
- **Net Revenue**: `invoices.amount - invoices.tax - invoices.discount WHERE payment_status = 'paid'`
- **Customer Lifetime Value (CLV)**: `AVG(total_paid_invoices_per_customer)`
- **Active User**: customer with `usage_events` in the last 30 days
- **Resolution Time**: `AVG(resolved_at - created_at) for support_tickets WHERE status = 'resolved'`

---

## 11. Open Questions (✅ All Resolved)

> All questions resolved on 2026-09-07. See Decision Log (Section 12) for details.

| Question | Resolution |
|---|---|
| Q1: Orchestration | LangGraph |
| Q2: LLM Provider | Provider-agnostic, start with Gemini Flash |
| Q3: Self-Consistency | Skip for MVP |
| Q4: Vector DB | ChromaDB |
| Q5: Frontend | Streamlit |
| Q6: Demo Database | SaaS schema (7 tables) |
| Q7: Dialect Scope | SQLite + PostgreSQL |
| Q8: Embeddings | Local sentence-transformers |
| Q9: Observability | Langfuse Cloud free tier |
| Q10: Demo Schema | Full 7-table SaaS schema |
| Q11: Deployment | Streamlit Cloud + Render |

---

## 12. Decision Log

> Every decision we make gets logged here with reasoning.

| # | Decision | Choice | Reasoning | Date |
|---|----------|--------|-----------|------|
| 1 | Orchestration Framework (Q1) | **LangGraph** | Gives us cycles, human-in-the-loop, persistence, and observability out of the box. Our clarification loop and retry logic are exactly the kind of cyclic, interruptible workflows LangGraph was built for. | 2026-09-07 |
| 2 | LLM Provider Strategy (Q2) | **Provider-agnostic, start with Gemini Flash** | Abstract behind a common interface, swap via config. No lock-in. Start with Gemini Flash free tier for generation. Can add Groq/others later without code changes. | 2026-09-07 |
| 3 | Self-Consistency (Q3) | **Skip for MVP, add later** | Keep v1 simple — single-pass generation. Self-consistency (Phase 5) becomes an optional enhancement once the core pipeline is solid. Reduces API calls and latency for v1. | 2026-09-07 |
| 4 | Vector Database (Q4) | **ChromaDB** | Zero-config, in-process, no Docker needed. Perfect for free deployment on Render. Can always migrate to Qdrant later if we need production-grade filtering. | 2026-09-07 |
| 5 | Frontend / Interface (Q5) | **Streamlit app** | Middle ground — more polished than Gradio, easier than React/Next.js. Good built-in chat components. Handles clarification dialogue flow naturally with `st.chat_message`. | 2026-09-07 |
| 6 | Demo Database (Q6) | **Realistic SaaS schema** | Subscriptions, MRR, churn, customer lifecycle. Showcases business knowledge requirements and ambiguity scenarios (e.g., "What's our revenue?" → gross vs net vs MRR). More impressive than Chinook for demos. | 2026-09-07 |
| 7 | Dialect Scope (Q7) | **SQLite (demos) + PostgreSQL (production)** | SQLite means zero infra to try it out. PostgreSQL for real use. SQLGlot handles transpilation between dialects. Lowest barrier to entry for new users. | 2026-09-07 |
| 8 | Embedding Model (Q8) | **Local sentence-transformers (all-MiniLM-L6-v2)** | Zero cost, no API calls, no rate limits. ~80MB model, works offline. Keeps us independent of any API provider for the RAG pipeline. | 2026-09-07 |
| 9 | Observability (Q9) | **Langfuse Cloud free tier** | Hosted, no extra infra to manage. 50K observations/month is plenty for a demo/prototype. Just needs API key in `.env`. | 2026-09-07 |
| 10 | Demo Schema (Q10) | **Full SaaS schema (7 tables)** | customers, subscriptions, invoices, support_tickets, products, usage_events, employees. Rich enough to demo ambiguity (name appears in both customers and employees, revenue can mean multiple things). | 2026-09-07 |
| 11 | Deployment Split (Q11) | **Streamlit Community Cloud + Render** | Frontend (Streamlit) on Streamlit Community Cloud (free). Backend (FastAPI) on Render free tier. Separation of concerns, both free. | 2026-09-07 |
| 12 | Self-Correction Loop Design | **Separate loops (2+2 retries), error classification, append-only history** | Three independent loops (syntax fix, runtime fix, clarification) with separate retry budgets of 2 each. Errors classified as recoverable vs unrecoverable to avoid wasting retries. Full error history accumulated and fed back to LLM on each correction attempt — prevents oscillation. Corrections always re-routed through validation (not directly to execution). Total worst-case: 5 LLM calls per question. | 2026-09-07 |
| 13 | Clarification Loop Management | **Caller-managed loop (not LangGraph interrupt)** | Graph terminates at END when clarification is needed. The caller (CLI/Streamlit) collects user input, runs handle_clarification, and re-invokes the graph. LangGraph interrupt() requires a checkpointer which adds infrastructure complexity. Caller-managed loop is simpler, works identically for CLI and Streamlit, and is easier to test. | 2026-09-08 |
| 14 | Rate Limit Handling | **Exponential backoff in Gemini client (3 retries, 10s initial)** | Free tier is 5 RPM / 20 RPD for gemini-3.6-flash. Instead of crashing on 429/503, the client retries with exponential backoff (10s, 20s, 40s). Only retries rate limits and server errors — client errors (400, 404) fail immediately. | 2026-09-08 |
| 15 | Validation: Three-layer security | **Keyword blocklist + syntax parse + AST walk** | Defense in depth. Keyword blocklist is fast and catches obvious cases (DROP, DELETE). SQLGlot parse catches syntax errors. AST walk catches mutations the keyword check might miss (e.g. creative SQL). Keyword check uses word-boundary regex to avoid false positives like "updated_at" matching "update". | 2026-09-08 |
| 16 | Groq as alternative provider | **GroqClient with qwen/qwen3.8-27b** | Gemini free tier daily quota (20 RPD) was too restrictive for development. Groq has much higher limits and sub-second inference. Both providers share the same BaseLLMClient interface — switch via LLM_PROVIDER env var. | 2026-09-08 |
| 17 | SQLite read-only enforcement | **PRAGMA query_only = ON** | Defense in depth — even if the AST blocklist misses a mutation, the DB itself blocks it. For PostgreSQL, this would be a read-only role instead. The timeout uses `threading.Timer` + `conn.interrupt()` since SQLite doesn't have native statement_timeout. | 2026-09-08 |
| 18 | Rate limiting approach | **In-memory sliding window (per-session, per-minute)** | Simple enough for the demo. Wired as an entry guard node in the graph — rejected requests never reach LLM calls, saving API quota. Not production-grade (no Redis, no persistence across restarts), but sufficient for preventing runaway loops and basic abuse. | 2026-09-08 |
