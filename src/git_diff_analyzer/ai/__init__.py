"""AI provider factory and package exports."""

from __future__ import annotations

from typing import Literal

from ..config import AppConfig
from .base import AIProvider, ProviderError
from .bedrock_provider import BedrockProvider
from .ollama_provider import OllamaProvider

__all__ = ["AIProvider", "ProviderError", "BedrockProvider", "OllamaProvider", "get_provider"]


def get_provider(
    provider: Literal["bedrock", "ollama"] | None,
    cfg: AppConfig,
) -> AIProvider:
    """
    Return an AIProvider instance.

    If provider is None, the default from cfg.analysis.default_provider is used.
    """
    chosen = provider or cfg.analysis.default_provider

    if chosen == "bedrock":
        return BedrockProvider(cfg.bedrock)
    if chosen == "ollama":
        return OllamaProvider(cfg.ollama)

    raise ValueError(f"Unknown provider: {chosen!r}. Choose 'bedrock' or 'ollama'.")
