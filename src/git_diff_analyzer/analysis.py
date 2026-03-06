"""Analysis orchestration: sends diffs to AI and parses the JSON response."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from .ai.base import AIProvider
from .ai.prompts import render_system_prompt, render_user_prompt
from .config import AppConfig
from .models import (
    AffectedCodeObject,
    AffectedDatabaseObject,
    AnalysisResult,
    DataChange,
    DiffBundle,
    Recommendation,
    SchemaChange,
)

logger = logging.getLogger(__name__)

# Regex to strip markdown code fences (```json ... ``` or ``` ... ```)
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    """Remove surrounding markdown code fences if present."""
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_json_object(text: str) -> str:
    """
    Attempt to extract the first top-level JSON object from text.

    Handles cases where the LLM emits preamble before the JSON.
    """
    start = text.find("{")
    if start == -1:
        return text
    # walk backwards from end to find matching closing brace
    end = text.rfind("}")
    if end == -1:
        return text[start:]
    return text[start : end + 1]


def _parse_ai_response(raw: str) -> tuple[dict, str | None]:
    """
    Parse the raw AI response string into a dict.

    Returns (parsed_dict, error_message).  error_message is None on success.
    """
    cleaned = _strip_code_fences(raw)
    cleaned = _extract_json_object(cleaned)

    first_exc = None
    try:
        return json.loads(cleaned), None
    except json.JSONDecodeError as exc:
        first_exc = exc
        logger.warning("JSON parse error: %s", exc)

    # Fallback: remove trailing commas before } or ] and retry
    repaired = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(repaired), f"JSON had trailing commas (auto-repaired): {first_exc}"
    except json.JSONDecodeError:
        pass

    # Total fallback: return minimal structure
    return {
        "summary": f"AI response could not be parsed as JSON. Raw response starts: {raw[:200]}",
        "impact_assessment": "",
        "schema_changes": [],
        "data_changes": [],
        "recommendations": [],
    }, f"JSON parse failed; raw response length={len(raw)}"


def _build_result(
    bundle: DiffBundle,
    data: dict,
    provider: AIProvider,
    raw_response: str,
    parse_error: str | None,
) -> AnalysisResult:
    schema_changes = [SchemaChange(**sc) for sc in data.get("schema_changes", [])]
    data_changes = [DataChange(**dc) for dc in data.get("data_changes", [])]
    recommendations = [Recommendation(**r) for r in data.get("recommendations", [])]
    affected_db = [AffectedDatabaseObject(**o) for o in data.get("affected_db_objects", [])]
    affected_code = [AffectedCodeObject(**o) for o in data.get("affected_code_objects", [])]

    return AnalysisResult(
        commit_hash=bundle.commit_hash,
        commit_message=bundle.commit_message,
        author=bundle.author,
        timestamp=bundle.timestamp,
        analyzed_at=datetime.now(tz=timezone.utc),
        summary=data.get("summary", ""),
        impact_assessment=data.get("impact_assessment", ""),
        schema_changes=schema_changes,
        data_changes=data_changes,
        recommendations=recommendations,
        affected_db_objects=affected_db,
        affected_code_objects=affected_code,
        ai_provider=provider.provider_name,
        ai_model=provider.model_name,
        raw_response=raw_response,
        parse_error=parse_error,
    )


def analyze(
    bundle: DiffBundle,
    provider: AIProvider,
    cfg: AppConfig,
) -> AnalysisResult:
    """
    Main entry point: takes a DiffBundle, calls the AI provider,
    and returns a parsed AnalysisResult.
    """
    logger.info(
        "Analyzing %s with %s/%s",
        bundle.commit_hash,
        provider.provider_name,
        provider.model_name,
    )

    system_prompt = render_system_prompt(
        database=cfg.snowflake.database,
        schema_name=cfg.snowflake.schema_name,
    )
    user_prompt = render_user_prompt(bundle)

    logger.debug("System prompt length: %d chars", len(system_prompt))
    logger.debug("User prompt length:   %d chars", len(user_prompt))

    raw_response = provider.complete(system_prompt, user_prompt)
    logger.debug("Raw AI response length: %d chars", len(raw_response))

    data, parse_error = _parse_ai_response(raw_response)

    if parse_error:
        logger.warning("AI response parse issue: %s", parse_error)

    return _build_result(bundle, data, provider, raw_response, parse_error)
