# Deploying SQLPilot

Three ways to run it, in increasing order of permanence:

| | What you get | Cost |
|---|---|---|
| [Docker Compose](#1-docker-compose-local) | API + UI on your machine, one command | free |
| [Render](#2-render-api) | Public HTTPS API | free tier |
| [Streamlit Community Cloud](#3-streamlit-community-cloud-ui) | Public chat UI, pointed at your API | free |

All three need the same thing first: **an LLM API key**. Everything else
(database, vector store, embeddings) runs locally inside the process.

---

## 1. Docker Compose (local)

The fastest path to a working system — no Python setup, no manual seeding.

```bash
cp .env.example .env      # then fill in GEMINI_API_KEY (or GROQ_API_KEY)
docker compose up --build
```

- UI → <http://localhost:8501>
- API docs → <http://localhost:8000/docs>

Both services run the same image. The `api` service bootstraps itself on first
boot (`docker/entrypoint.sh`): it seeds `data/demo.db` and builds the ChromaDB
index into a named volume, then starts uvicorn. The `ui` service waits for the
API's health check and talks to it over the compose network at `http://api:8000`.

**First boot takes a few minutes** — it downloads the embedding model and seeds
the database. Later starts reuse the `sqlpilot-data` volume and come up in
seconds.

Useful commands:

```bash
docker compose logs -f api        # watch the pipeline
docker compose down               # stop, keep the seeded data
docker compose down -v            # stop and wipe the volume (forces a re-seed)
docker compose run --rm api python -m app.cli "How many customers do we have?"
```

### Configuration

Everything is environment variables, read by `app/config.py`. Compose passes
your `.env` through to both services; see `.env.example` for the full list. The
ones that matter most:

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `groq` |
| `LLM_MODEL` | `gemini-2.0-flash` | must match the provider |
| `GEMINI_API_KEY` / `GROQ_API_KEY` | — | at least one is required |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | — | optional; tracing no-ops without them |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | **must match your project's region**, or you get silent 401s |
| `STATEMENT_TIMEOUT_MS` | `30000` | query kill switch |
| `MAX_RESULT_ROWS` | `1000` | row cap |
| `RATE_LIMIT_PER_MINUTE` | `20` | per session |
| `SQLPILOT_API_URL` | `http://localhost:8000` | UI → API address (compose sets this to `http://api:8000`) |

`SQLPILOT_BOOTSTRAP=1` is what tells a container to seed the DB and index RAG
before starting. Compose sets it on `api` only — the UI never touches the
database.

---

## 2. Render (API)

Render's free web-service tier runs the Dockerfile as-is.

**Blueprint (recommended).** `render.yaml` in the repo root describes the
service. In the Render dashboard: **New → Blueprint**, point it at your fork,
and Render will prompt for the secret env vars (`GEMINI_API_KEY` /
`GROQ_API_KEY`, and the Langfuse keys if you want tracing).

**Manual setup**, if you'd rather click through it:

1. **New → Web Service**, connect the repo.
2. Runtime **Docker**, dockerfile path `./Dockerfile`, plan **Free**.
3. Health check path: `/health`.
4. Environment variables — at minimum:
   ```
   SQLPILOT_BOOTSTRAP=1
   LLM_PROVIDER=gemini
   LLM_MODEL=gemini-2.0-flash
   GEMINI_API_KEY=<your key>
   ```
   Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` for tracing.
5. Deploy. First boot seeds the demo DB and builds the index before uvicorn
   starts, so give it a few minutes before the health check goes green.

### Free-tier caveats, honestly

- **No persistent disk.** `data/` is ephemeral, so the demo database and vector
  index are rebuilt on every cold boot. That's fine here — the demo data is
  generated, not precious — and it keeps the service stateless. If you point
  SQLPilot at a real database, set `DB_TYPE`/`POSTGRES_URL` instead and the
  local file goes away entirely.
- **Instances spin down when idle.** The first request after a spin-down pays
  the full cold-boot cost (seed + index + embedding-model download), which is
  well past a typical HTTP timeout. Expect to reload once.
- **512 MB RAM is tight.** ChromaDB plus the ONNX embedding runtime fit, but
  there isn't much headroom. If you see OOM restarts, either move to a paid
  instance or run ChromaDB as a separate service.
- **In-memory state doesn't survive restarts, and doesn't span workers.** The
  rate limiter (`app/security/rate_limiter.py`) and the clarification session
  store (`app/api/session_store.py`) are both process-local dicts. Run a
  **single** worker — multiple workers would route `/clarify` to a process that
  never saw the matching `/query`. Making this multi-worker means moving both
  into Redis.

### Auto-deploy from GitHub

`.github/workflows/deploy.yml` pings a Render deploy hook after CI passes on
`main`. To enable it: **Render → your service → Settings → Deploy Hook**, copy
the URL, and add it to the repo as the secret `RENDER_DEPLOY_HOOK_URL`
(**Settings → Secrets and variables → Actions**). Without that secret the
workflow logs a skip and exits cleanly, so forks aren't broken by it.

Render's own "Auto-Deploy on push" setting does the same thing without any
GitHub Actions involvement — use whichever you prefer, not both.

---

## 3. Streamlit Community Cloud (UI)

The frontend is a thin HTTP client, so it deploys on its own.

1. Push your fork to GitHub.
2. At <https://share.streamlit.io>: **New app** → pick the repo/branch →
   main file `streamlit_app.py`.
3. **Advanced settings → Secrets**, point it at your Render API:
   ```toml
   SQLPILOT_API_URL = "https://your-service.onrender.com"
   ```
   Streamlit exposes secrets as environment variables, which is exactly what
   `streamlit_app.py` reads.
4. Deploy.

Streamlit Cloud installs the root `requirements.txt`, which pulls the whole
backend for a UI that only needs `streamlit` and `httpx`. It works, just
slowly. If build time bothers you, put a two-line `requirements.txt` in a
UI-only fork.

Two things to check if the UI can't reach the API: CORS is already permissive
(`allow_origins=["*"]` in `app/main.py`), and a spun-down free Render instance
will time out the first request — reload once.

---

## Verifying a deployment

```bash
BASE=https://your-service.onrender.com

curl -fsS $BASE/health
curl -fsS $BASE/schema | head -c 400
curl -fsS -X POST $BASE/query \
  -H 'content-type: application/json' \
  -d '{"question":"How many customers do we have?"}'
```

Expected: `{"status":"ok",...}`, a table listing, and a `status: "success"`
response carrying `sql`, `rows`, and `explanation`. An ambiguous question comes
back as `status: "clarification_needed"` with a `session_id` to POST to
`/clarify`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `GEMINI_API_KEY is not set` / `GROQ_API_KEY is not set` | key missing from the environment | check `.env` locally, or the service's env vars in Render |
| `Demo database not found at data/demo.db` | container started without bootstrapping | set `SQLPILOT_BOOTSTRAP=1`, or run `python scripts/seed_database.py` |
| `/clarify` returns 404 for a real session | more than one worker, or the process restarted | run a single worker; the session store is in-memory |
| Traces never appear in Langfuse | `LANGFUSE_HOST` doesn't match the key's region | copy the exact host from Langfuse → Settings |
| UI shows "Could not reach SQLPilot API" | wrong `SQLPILOT_API_URL`, or the API is cold-starting | check the URL, then reload once |
| Container OOMs on Render free tier | 512 MB is tight for Chroma + ONNX | move to a paid instance, or externalize ChromaDB |
