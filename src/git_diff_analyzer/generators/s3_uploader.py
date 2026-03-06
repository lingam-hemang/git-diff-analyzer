"""Upload analysis output files to Amazon S3."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_PDF_CONTENT_TYPE = "application/pdf"
_SQL_CONTENT_TYPE = "text/plain"


def upload_to_s3(
    local_path: Path,
    bucket: str,
    key: str,
    region: Optional[str] = None,
) -> str:
    """Upload a single file to S3 and return the s3://bucket/key URI."""
    import boto3  # lazy import — boto3 not required for non-AWS usage

    content_type = _PDF_CONTENT_TYPE if local_path.suffix.lower() == ".pdf" else _SQL_CONTENT_TYPE

    kwargs: Dict = {}
    if region:
        kwargs["region_name"] = region

    client = boto3.client("s3", **kwargs)
    client.upload_file(
        Filename=str(local_path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={"ContentType": content_type},
    )
    uri = f"s3://{bucket}/{key}"
    logger.info("Uploaded %s → %s", local_path, uri)
    return uri


def upload_analysis_output(
    pdf_path: Optional[Path],
    dml_dir: Optional[Path],
    bucket: str,
    prefix: str,
    commit_hash: str,
    region: Optional[str] = None,
) -> Dict[str, object]:
    """
    Upload all output for a commit to S3.

    Returns a dict with keys:
      - pdf_uri:    s3 URI for the PDF (or None)
      - dml_uris:   list of s3 URIs for SQL scripts
      - run_all_uri: s3 URI for 000_run_all.sql (or None)
    """
    short = commit_hash[:12]
    pdf_uri: Optional[str] = None
    dml_uris: List[str] = []
    run_all_uri: Optional[str] = None

    if pdf_path and pdf_path.is_file():
        key = f"{prefix}{short}/{pdf_path.name}"
        pdf_uri = upload_to_s3(pdf_path, bucket, key, region)

    if dml_dir and dml_dir.is_dir():
        for sql_file in sorted(dml_dir.glob("*.sql")):
            key = f"{prefix}{short}/{sql_file.name}"
            uri = upload_to_s3(sql_file, bucket, key, region)
            if sql_file.name.startswith("000_run_all"):
                run_all_uri = uri
            else:
                dml_uris.append(uri)

    return {"pdf_uri": pdf_uri, "dml_uris": dml_uris, "run_all_uri": run_all_uri}
