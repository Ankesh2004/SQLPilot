"""
Gemini Flash implementation of the LLM interface.

uses the google-genai SDK (not the old google-generativeai one).
includes rate limit handling with backoff since the free tier is tight.
"""

import json
import time
import logging
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.llm.base import BaseLLMClient
from app.config import settings
from app.observability.tracing import log_generation

logger = logging.getLogger(__name__)

# free tier is stingy — retry with backoff instead of crashing
MAX_RETRIES = 3
INITIAL_BACKOFF = 10  # seconds


class GeminiClient(BaseLLMClient):
    """talks to Gemini Flash via the google-genai SDK."""

    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set -- check your .env file")

        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.llm_model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """plain text generation."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=0.0,  # deterministic for SQL generation
        )

        response = self._call_with_retry(prompt, config)
        text = response.text.strip()
        self._log_generation("gemini.generate", prompt, text, response)
        return text

    def generate_structured(self, prompt: str, system_prompt: str = "") -> dict:
        """
        generate a JSON response from the LLM.

        we ask for JSON output and parse it. if the LLM wraps it in markdown
        code fences (```json ... ```), we strip those before parsing.
        """
        # tell the model we want JSON back
        full_system = (system_prompt + "\n\n" if system_prompt else "")
        full_system += "Respond ONLY with valid JSON. No markdown, no explanation, no code fences."

        config = types.GenerateContentConfig(
            system_instruction=full_system,
            temperature=0.0,
            response_mime_type="application/json",
        )

        response = self._call_with_retry(prompt, config)
        raw = response.text.strip()
        self._log_generation("gemini.generate_structured", prompt, raw, response)

        # sometimes the model wraps JSON in code fences anyway
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}\nRaw: {raw}")
            return {"sql": raw, "assumptions": "Failed to parse structured response"}

    def _log_generation(self, name: str, prompt: str, output: str, response) -> None:
        """report token usage for this call to Langfuse (no-op if tracing is disabled)."""
        usage_meta = getattr(response, "usage_metadata", None)
        usage = None
        if usage_meta is not None:
            usage = {
                "input": getattr(usage_meta, "prompt_token_count", None),
                "output": getattr(usage_meta, "candidates_token_count", None),
                "total": getattr(usage_meta, "total_token_count", None),
                "unit": "TOKENS",
            }
        log_generation(name, self.model, prompt, output, usage=usage)

    def _call_with_retry(self, prompt, config):
        """
        call the API with exponential backoff on rate limits (429) and server errors (503).

        the free tier for gemini-3.6-flash is tight (5 RPM, 20 RPD).
        instead of crashing, we wait and retry.
        """
        backoff = INITIAL_BACKOFF
        for attempt in range(MAX_RETRIES):
            try:
                return self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
            except (ClientError, ServerError) as e:
                status = getattr(e, 'status', None) or ""
                error_str = str(e)

                # only retry on rate limits (429) and server overload (503)
                is_retryable = "429" in error_str or "503" in error_str or "RESOURCE_EXHAUSTED" in error_str
                if not is_retryable or attempt == MAX_RETRIES - 1:
                    raise

                logger.warning(f"Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), waiting {backoff}s...")
                time.sleep(backoff)
                backoff *= 2  # exponential backoff
