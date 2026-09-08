"""FastAPI application entrypoint."""

from dotenv import load_dotenv

# load .env before anything else touches config (mirrors app/cli.py)
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.models.schemas import HealthResponse

app = FastAPI(
    title="SQLPilot",
    description="Text-to-SQL with clarification — asks before it guesses",
    version="0.1.0",
)

# permissive by default -- this is a local/demo API with no auth, not a
# multi-tenant production service
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok", "version": "0.1.0"}
