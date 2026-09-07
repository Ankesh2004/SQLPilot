"""
Abstract LLM interface.

every provider (Gemini, Groq, etc.) implements this.
swap providers by changing LLM_PROVIDER in .env — no code changes needed.
"""

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """common interface all LLM providers must implement."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """
        send a prompt to the LLM and get back a text response.

        Args:
            prompt: the user/task prompt
            system_prompt: optional system-level instructions

        Returns:
            the LLM's text response
        """
        ...

    @abstractmethod
    def generate_structured(self, prompt: str, system_prompt: str = "") -> dict:
        """
        same as generate() but expects a JSON response.
        used for SQL generation where we want structured output
        (sql + assumptions in a predictable format).

        Returns:
            parsed dict from the LLM's JSON response
        """
        ...
