"""Ollama provider using httpx (local LLM REST API)."""

from __future__ import annotations

import logging

from ..config import OllamaConfig
from .base import AIProvider, ProviderError

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    def __init__(self, cfg: OllamaConfig) -> None:
        self._cfg = cfg

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._cfg.model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise ProviderError("httpx is not installed. Run: pip install httpx") from exc

        url = f"{self._cfg.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._cfg.temperature,
                "num_predict": self._cfg.max_tokens,
            },
        }

        logger.debug("Calling Ollama model %s at %s", self._cfg.model, url)

        try:
            with httpx.Client(timeout=self._cfg.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["message"]["content"]
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Cannot connect to Ollama at {self._cfg.base_url}. "
                "Is Ollama running? (ollama serve)"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Ollama HTTP error {exc.response.status_code}: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc
