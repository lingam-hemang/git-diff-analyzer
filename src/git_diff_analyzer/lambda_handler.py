"""AWS Lambda handler for git-diff-analyzer.

Triggered by GitHub webhooks or AWS CodeCommit events.
Clones the repo, runs analysis, and uploads output to S3.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .config import load_config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ── Event parsing ─────────────────────────────────────────────────────────────

def _parse_github_event(event: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Parse a GitHub webhook event.

    Returns (clone_url, commit_sha, ref).
    Raises ValueError if required fields are missing.
    """
    body_raw = event.get("body") or "{}"
    if isinstance(body_raw, str):
        payload = json.loads(body_raw)
    else:
        payload = body_raw

    repo = payload.get("repository", {})
    clone_url = repo.get("clone_url") or repo.get("ssh_url")
    if not clone_url:
        raise ValueError("GitHub event missing repository.clone_url")

    commit_sha = payload.get("after")
    if not commit_sha:
        raise ValueError("GitHub event missing 'after' (commit SHA)")

    ref = payload.get("ref", "refs/heads/main")
    return clone_url, commit_sha, ref


def _parse_codecommit_event(event: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Parse an AWS CodeCommit CloudWatch Events trigger.

    Returns (clone_url, commit_sha, ref).
    Raises ValueError if required fields are missing.
    """
    detail = event.get("detail", {})
    repo_name = detail.get("repositoryName")
    commit_id = detail.get("commitId")
    ref = detail.get("referenceFullName", "refs/heads/main")

    if not repo_name:
        raise ValueError("CodeCommit event missing detail.repositoryName")
    if not commit_id:
        raise ValueError("CodeCommit event missing detail.commitId")

    region = event.get("region") or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    clone_url = f"https://git-codecommit.{region}.amazonaws.com/v1/repos/{repo_name}"
    return clone_url, commit_id, ref


def _detect_event_source(event: Dict[str, Any]) -> str:
    """Return 'github', 'codecommit', or raise ValueError."""
    if "body" in event:
        return "github"
    if "detail" in event and "repositoryName" in event.get("detail", {}):
        return "codecommit"
    raise ValueError("Cannot determine event source (not GitHub or CodeCommit)")


def _verify_github_signature(body: str, signature_header: str, secret: str) -> bool:
    """Verify X-Hub-Signature-256 header from GitHub."""
    expected = "sha256=" + hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Core pipeline ─────────────────────────────────────────────────────────────

def _run_analysis(clone_url: str, commit_sha: str, cfg: Any) -> Dict[str, Any]:
    """
    Clone the repo, analyze the commit, generate outputs, upload to S3.

    Returns a summary dict.
    """
    from git import Repo

    from .ai import get_provider
    from .analysis import analyze
    from .generators.dml_generator import generate_dml_scripts
    from .generators.pdf_generator import generate_pdf
    from .generators.s3_uploader import upload_analysis_output
    from .git_integration import get_commit_diff

    tmp_dir = Path(tempfile.mkdtemp(prefix="gda_"))
    try:
        logger.info("Cloning %s into %s", clone_url, tmp_dir)
        Repo.clone_from(clone_url, str(tmp_dir))

        bundle = get_commit_diff(tmp_dir, commit_ref=commit_sha, cfg=cfg.analysis)

        ai_provider = get_provider(None, cfg)
        result = analyze(bundle, ai_provider, cfg)

        short_hash = commit_sha[:12]
        docs_dir = Path(tempfile.mkdtemp(prefix="gda_pdf_"))
        dml_dir = Path(tempfile.mkdtemp(prefix="gda_dml_")) / short_hash
        dml_dir.mkdir(parents=True)

        pdf_path = docs_dir / f"analysis_{short_hash}.pdf"
        generate_pdf(result, pdf_path)
        scripts, _ = generate_dml_scripts(result, dml_dir, cfg.snowflake)

        s3_result: Dict[str, Any] = {}
        if cfg.s3.bucket:
            s3_result = upload_analysis_output(
                pdf_path=pdf_path,
                dml_dir=dml_dir if scripts else None,
                bucket=cfg.s3.bucket,
                prefix=cfg.s3.prefix,
                commit_hash=commit_sha,
                region=cfg.s3.region,
            )

        return {
            "commit_hash": commit_sha,
            "summary": result.summary,
            "schema_changes": len(result.schema_changes),
            "data_changes": len(result.data_changes),
            "affected_db_objects": len(result.affected_db_objects),
            "affected_code_objects": len(result.affected_code_objects),
            "s3": s3_result,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Lambda entry point ────────────────────────────────────────────────────────

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda entry point."""
    # Determine config path from env var or use defaults
    config_env = os.environ.get("GDA_CONFIG")
    cfg = load_config(Path(config_env) if config_env else None)

    try:
        source = _detect_event_source(event)
    except ValueError as exc:
        logger.error("Unknown event source: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}

    # Verify GitHub webhook signature if secret is configured
    if source == "github" and cfg.aws_lambda.github_webhook_secret:
        headers = event.get("headers") or {}
        sig_header = headers.get("X-Hub-Signature-256") or headers.get("x-hub-signature-256", "")
        body_raw = event.get("body", "")
        if not _verify_github_signature(body_raw, sig_header, cfg.aws_lambda.github_webhook_secret):
            logger.warning("GitHub webhook signature verification failed")
            return {"statusCode": 401, "body": json.dumps({"error": "Invalid signature"})}

    try:
        if source == "github":
            clone_url, commit_sha, ref = _parse_github_event(event)
        else:
            clone_url, commit_sha, ref = _parse_codecommit_event(event)
    except ValueError as exc:
        logger.error("Event parsing error: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}

    logger.info("Processing %s commit %s (ref: %s)", source, commit_sha, ref)

    try:
        summary = _run_analysis(clone_url, commit_sha, cfg)
    except Exception as exc:
        logger.exception("Analysis pipeline failed: %s", exc)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}

    return {"statusCode": 200, "body": json.dumps(summary)}
