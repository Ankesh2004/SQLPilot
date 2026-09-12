"""
Ollama implementation of the LLM interface.

runs a local model via Ollama's REST API (http://localhost:11434 by default) --
no API key, no rate limits, useful for eval runs that would otherwise burn
through a cloud provider's free-tier daily quota.
"""

import json
import logging
import httpx

from app.llm.base import BaseLLMClient
from app.config import settings
from app.observability.tracing import log_generation

logger = logging.getLogger(__name__)


class OllamaClient(BaseLLMClient):
    """talks to a local Ollama server."""

    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.llm_model

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """plain text generation."""
        response = self._call(prompt, system_prompt)
        text = response["response"].strip()
        self._log_generation("ollama.generate", prompt, text, response)
        return text

    def generate_structured(self, prompt: str, system_prompt: str = "") -> dict:
        """
        generate a JSON response from the LLM.

        Ollama's `format: "json"` forces valid JSON output. if the model wraps
        it in markdown code fences anyway, we strip those before parsing.
        """
        full_system = (system_prompt + "\n\n" if system_prompt else "")
        full_system += "Respond ONLY with valid JSON. No markdown, no explanation, no code fences."

        response = self._call(prompt, full_system, json_mode=True)
        raw = response["response"].strip()
        self._log_generation("ollama.generate_structured", prompt, raw, response)

        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Ollama JSON response: {e}\nRaw: {raw}")
            return {"sql": raw, "assumptions": "Failed to parse structured response"}

    def _call(self, prompt: str, system_prompt: str = "", json_mode: bool = False) -> dict:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or None,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        if json_mode:
            payload["format"] = "json"

        resp = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=180.0)
        resp.raise_for_status()
        return resp.json()

    def _log_generation(self, name: str, prompt: str, output: str, response: dict) -> None:
        """report token usage for this call to Langfuse (no-op if tracing is disabled)."""
        prompt_tokens = response.get("prompt_eval_count")
        output_tokens = response.get("eval_count")
        usage = None
        if prompt_tokens is not None or output_tokens is not None:
            usage = {
                "input": prompt_tokens,
                "output": output_tokens,
                "total": (prompt_tokens or 0) + (output_tokens or 0),
                "unit": "TOKENS",
            }
        log_generation(name, self.model, prompt, output, usage=usage)
