"""
Groq implementation of the LLM interface.

groq has high RPM limits and fast inference — much better for testing
than gemini free tier (5 RPM / 20 RPD).
"""

import json
import time
import logging
from groq import Groq

from app.llm.base import BaseLLMClient
from app.config import settings
from app.observability.tracing import log_generation

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 5


class GroqClient(BaseLLMClient):
    """talks to Groq's API."""

    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set -- check your .env file")

        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.llm_model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """plain text generation."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._call_with_retry(messages, json_mode=False)
        text = response.choices[0].message.content.strip()
        self._log_generation("groq.generate", prompt, text, response)
        return text

    def generate_structured(self, prompt: str, system_prompt: str = "") -> dict:
        """
        generate a JSON response.

        groq supports JSON mode natively via response_format.
        """
        full_system = (system_prompt + "\n\n" if system_prompt else "")
        full_system += "Respond ONLY with valid JSON. No markdown, no explanation, no code fences."

        messages = []
        if full_system:
            messages.append({"role": "system", "content": full_system})
        messages.append({"role": "user", "content": prompt})

        response = self._call_with_retry(messages, json_mode=True)
        raw = response.choices[0].message.content.strip()
        self._log_generation("groq.generate_structured", prompt, raw, response)

        # strip code fences if the model wraps JSON anyway
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Groq JSON response: {e}\nRaw: {raw}")
            return {"sql": raw, "assumptions": "Failed to parse structured response"}

    def _log_generation(self, name: str, prompt: str, output: str, response) -> None:
        """report token usage for this call to Langfuse (no-op if tracing is disabled)."""
        usage_obj = getattr(response, "usage", None)
        usage = None
        if usage_obj is not None:
            usage = {
                "input": getattr(usage_obj, "prompt_tokens", None),
                "output": getattr(usage_obj, "completion_tokens", None),
                "total": getattr(usage_obj, "total_tokens", None),
                "unit": "TOKENS",
            }
        log_generation(name, self.model, prompt, output, usage=usage)

    def _call_with_retry(self, messages, json_mode=False):
        """call with backoff on rate limits."""
        backoff = INITIAL_BACKOFF

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 2048,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(MAX_RETRIES):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                error_str = str(e)
                is_retryable = "429" in error_str or "503" in error_str or "rate" in error_str.lower()

                if not is_retryable or attempt == MAX_RETRIES - 1:
                    raise

                logger.warning(f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), waiting {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
