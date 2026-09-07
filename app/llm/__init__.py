"""
Provider-agnostic LLM client layer.

call get_llm_client() to get the right provider based on config.
"""

from app.llm.base import BaseLLMClient
from app.config import settings


def get_llm_client() -> BaseLLMClient:
    """factory that returns the configured LLM provider."""
    if settings.llm_provider == "gemini":
        from app.llm.gemini import GeminiClient
        return GeminiClient()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
