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
    elif settings.llm_provider == "groq":
        from app.llm.groq_client import GroqClient
        return GroqClient()
    elif settings.llm_provider == "ollama":
        from app.llm.ollama_client import OllamaClient
        return OllamaClient()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
