"""
Central config — pulls everything from environment variables.
Uses pydantic-settings so we get validation + type coercion for free.
"""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """all the knobs for SQLPilot, loaded from .env or environment."""

    # --- LLM ---
    llm_provider: Literal["gemini", "groq"] = "gemini"
    llm_model: str = "gemini-2.0-flash"
    gemini_api_key: str = ""
    groq_api_key: str = ""  # optional, for future use

    # --- Database ---
    db_type: Literal["sqlite", "postgres"] = "sqlite"
    sqlite_db_path: str = "data/demo.db"
    postgres_url: str = ""

    # --- RAG ---
    chroma_persist_dir: str = "data/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"

    # --- Observability ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Pipeline ---
    max_retries: int = 3
    statement_timeout_ms: int = 30000
    max_result_rows: int = 1000
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # don't blow up on unknown env vars
    }


# singleton — import this wherever you need config
settings = Settings()
