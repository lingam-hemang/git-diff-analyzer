"""AWS Bedrock provider using boto3 (Claude models via Converse API)."""

from __future__ import annotations

import json
import logging

from ..config import BedrockConfig
from .base import AIProvider, ProviderError

logger = logging.getLogger(__name__)


class BedrockProvider(AIProvider):
    def __init__(self, cfg: BedrockConfig) -> None:
        self._cfg = cfg
        self._client = self._build_client()

    def _build_client(self):  # type: ignore[return]
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError("boto3 is not installed. Run: pip install boto3") from exc

        kwargs: dict = {"region_name": self._cfg.region}
        if self._cfg.profile:
            session = boto3.Session(profile_name=self._cfg.profile)
            return session.client("bedrock-runtime", **kwargs)

        return boto3.client("bedrock-runtime", **kwargs)

    @property
    def provider_name(self) -> str:
        return "bedrock"

    @property
    def model_name(self) -> str:
        return self._cfg.model_id

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        logger.debug("Calling Bedrock model %s", self._cfg.model_id)

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._cfg.max_tokens,
            "temperature": self._cfg.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        try:
            response = self._client.invoke_model(
                modelId=self._cfg.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            raw = response["body"].read()
            data = json.loads(raw)
            return data["content"][0]["text"]
        except Exception as exc:
            raise ProviderError(f"Bedrock call failed: {exc}") from exc
