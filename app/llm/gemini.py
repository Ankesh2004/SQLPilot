"""
Gemini Flash implementation of the LLM interface.

uses the google-genai SDK (not the old google-generativeai one).
"""

import json
import logging
from google import genai
from google.genai import types

from app.llm.base import BaseLLMClient
from app.config import settings

logger = logging.getLogger(__name__)


class GeminiClient(BaseLLMClient):
    """talks to Gemini Flash via the google-genai SDK."""

    def __init__(self):
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set — check your .env file")

        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.llm_model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """plain text generation."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=0.0,  # deterministic for SQL generation
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )

        return response.text.strip()

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

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )

        raw = response.text.strip()

        # sometimes the model wraps JSON in code fences anyway
        if raw.startswith("```"):
            # strip ```json\n...\n```
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}\nRaw: {raw}")
            # return a best-effort dict so the pipeline doesn't crash
            return {"sql": raw, "assumptions": "Failed to parse structured response"}
