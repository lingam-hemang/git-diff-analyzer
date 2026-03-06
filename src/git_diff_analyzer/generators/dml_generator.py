"""Snowflake DML/DDL script generator with transaction safety."""

from __future__ import annotations

import logging
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from ..config import SnowflakeConfig
from ..models import AnalysisResult, DataChange, DMLScript, SchemaChange, ScriptType

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 40) -> str:
    slug = _SLUG_RE.sub("_", text.lower()).strip("_")
    return slug[:max_len].strip("_")


def _script_header(
    seq: int,
    script_type: ScriptType,
    description: str,
    commit_hash: str,
    cfg: SnowflakeConfig,
) -> str:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return textwrap.dedent(f"""\
        -- =============================================================================
        -- Script  : {seq:03d}_{script_type.value.lower()}_{_slugify(description)}.sql
        -- Type    : {script_type.value}
        -- Commit  : {commit_hash}
        -- Generated: {now}
        -- Database: {cfg.database}
        -- Schema  : {cfg.schema_name}
        -- =============================================================================

        USE DATABASE {cfg.database};
        USE SCHEMA {cfg.schema_name};
        {"USE WAREHOUSE " + cfg.warehouse + ";" if cfg.warehouse else ""}
        {"USE ROLE " + cfg.role + ";" if cfg.role else ""}

    """).rstrip() + "\n\n"


def _wrap_transaction(sql: str, cfg: SnowflakeConfig) -> str:
    if not cfg.use_transactions:
        return sql
    return textwrap.dedent(f"""\
        BEGIN TRANSACTION;

        {sql.strip()}

        -- If you have verified the changes above, replace ROLLBACK with COMMIT:
        ROLLBACK;
    """)


def _make_ddl_script(
    seq: int,
    change: SchemaChange,
    commit_hash: str,
    cfg: SnowflakeConfig,
) -> DMLScript:
    slug = _slugify(f"{change.change_type}_{change.table}")
    filename = f"{seq:03d}_ddl_{slug}.sql"
    header = _script_header(seq, ScriptType.DDL, change.description, commit_hash, cfg)
    body = _wrap_transaction(change.snowflake_sql, cfg)
    return DMLScript(
        sequence=seq,
        script_type=ScriptType.DDL,
        filename=filename,
        description=change.description,
        sql_content=header + body,
        table=change.table,
        is_breaking=change.is_breaking,
    )


def _make_dml_script(
    seq: int,
    change: DataChange,
    commit_hash: str,
    cfg: SnowflakeConfig,
) -> DMLScript:
    slug = _slugify(f"{change.operation}_{change.table}")
    filename = f"{seq:03d}_dml_{slug}.sql"
    header = _script_header(seq, ScriptType.DML, change.description, commit_hash, cfg)
    body = _wrap_transaction(change.snowflake_sql, cfg)
    return DMLScript(
        sequence=seq,
        script_type=ScriptType.DML,
        filename=filename,
        description=change.description,
        sql_content=header + body,
        table=change.table,
    )


def _make_run_all(scripts: list[DMLScript], commit_hash: str, cfg: SnowflakeConfig) -> str:
    """Generate a master 000_run_all.sql that sources every script in order."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "-- =============================================================================",
        "-- 000_run_all.sql — Master execution script",
        f"-- Commit  : {commit_hash}",
        f"-- Generated: {now}",
        "-- Run each script in Snowsight or SnowSQL in the order listed below.",
        "-- IMPORTANT: review each script individually before executing in production.",
        "-- =============================================================================",
        "",
        f"USE DATABASE {cfg.database};",
        f"USE SCHEMA {cfg.schema_name};",
        "",
        "-- Execution order (DDL first, then DML):",
        "-- ----------------------------------------",
    ]
    for script in sorted(scripts, key=lambda s: s.sequence):
        breaking_tag = "  [BREAKING CHANGE]" if script.is_breaking else ""
        lines.append(
            f"-- {script.sequence:03d}. [{script.script_type.value}] "
            f"{script.filename}{breaking_tag}"
        )
    lines += [
        "",
        "-- Execute each file manually in order, e.g. (SnowSQL):",
    ]
    for script in sorted(scripts, key=lambda s: s.sequence):
        lines.append(f"--   !source {script.filename}")
    lines.append("")
    return "\n".join(lines)


def generate_dml_scripts(
    result: AnalysisResult,
    output_dir: Path,
    cfg: SnowflakeConfig,
) -> tuple[list[DMLScript], Path | None]:
    """
    Write numbered SQL scripts to output_dir.

    DDL scripts come first (lower sequence numbers), then DML.
    Returns (list_of_DMLScript, run_all_path).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    scripts: list[DMLScript] = []
    seq = 1

    # DDL first
    for change in result.schema_changes:
        script = _make_ddl_script(seq, change, result.commit_hash, cfg)
        scripts.append(script)
        seq += 1

    # DML next (respecting requires_ddl_first ordering naturally since DDL seq < DML seq)
    # Sort DML: tables required by DDL first
    ddl_tables = {sc.table for sc in result.schema_changes}
    dml_sorted = sorted(
        result.data_changes,
        key=lambda dc: (0 if dc.depends_on_table in ddl_tables else 1, dc.table),
    )
    for change in dml_sorted:
        script = _make_dml_script(seq, change, result.commit_hash, cfg)
        scripts.append(script)
        seq += 1

    if not scripts:
        logger.info("No schema/data changes to write for %s", result.commit_hash)
        return [], None

    # Write individual scripts
    for script in scripts:
        path = output_dir / script.filename
        path.write_text(script.sql_content, encoding="utf-8")
        logger.debug("Wrote %s", path)

    # Write master run-all
    run_all_content = _make_run_all(scripts, result.commit_hash, cfg)
    run_all_path = output_dir / "000_run_all.sql"
    run_all_path.write_text(run_all_content, encoding="utf-8")
    logger.info("Wrote %d SQL scripts + run-all to %s", len(scripts), output_dir)

    return scripts, run_all_path
