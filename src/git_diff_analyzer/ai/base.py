"""Abstract base class for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    """Common interface all AI providers must implement."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send a prompt to the underlying model and return the raw text response.

        Implementations should raise ProviderError on unrecoverable failures.
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier, e.g. 'bedrock' or 'ollama'."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier as reported by the provider."""


class ProviderError(Exception):
    """Raised when an AI provider call fails."""
