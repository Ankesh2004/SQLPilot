"""FastAPI application entrypoint. Wired up in later phases."""

from fastapi import FastAPI

app = FastAPI(
    title="SQLPilot",
    description="Text-to-SQL with clarification — asks before it guesses",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
