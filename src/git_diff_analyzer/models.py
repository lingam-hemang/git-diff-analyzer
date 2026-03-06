"""Shared Pydantic data models for the git diff analyzer pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class FileDiff(BaseModel):
    """Represents the diff for a single file in a commit."""

    path: str
    change_type: ChangeType
    old_path: Optional[str] = None  # populated for renames
    diff_text: str
    additions: int = 0
    deletions: int = 0


class DiffBundle(BaseModel):
    """Complete diff payload for one commit or commit range."""

    repo_path: str
    commit_hash: str  # single commit SHA or 'from..to' range notation
    commit_message: str
    author: str
    timestamp: datetime
    files: List[FileDiff] = Field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0

    @property
    def combined_diff(self) -> str:
        """Return all file diffs concatenated (used for prompt building)."""
        parts: List[str] = []
        for f in self.files:
            parts.append(f"=== {f.change_type.value.upper()}: {f.path} ===")
            parts.append(f.diff_text)
        return "\n".join(parts)


# ── AI output models ──────────────────────────────────────────────────────────

class SchemaChange(BaseModel):
    """Describes a database schema change detected from the diff."""

    table: str = Field(description="Snowflake table name in UPPER_SNAKE_CASE")
    change_type: str = Field(description="e.g. ADD_COLUMN, DROP_COLUMN, CREATE_TABLE, ALTER_COLUMN")
    description: str
    snowflake_sql: str = Field(description="The DDL SQL statement for this change")
    is_breaking: bool = False
    migration_notes: str = ""


class DataChange(BaseModel):
    """Describes a DML/data-manipulation change implied by the diff."""

    table: str = Field(description="Snowflake table name in UPPER_SNAKE_CASE")
    operation: str = Field(description="INSERT, UPDATE, DELETE, MERGE, or TRUNCATE")
    description: str
    snowflake_sql: str = Field(description="The DML SQL statement for this change")
    requires_ddl_first: bool = False
    depends_on_table: Optional[str] = None


class Recommendation(BaseModel):
    category: str  # e.g. "Performance", "Data Quality", "Security"
    text: str
    priority: str = "medium"  # low | medium | high


class AffectedDatabaseObject(BaseModel):
    """A database object (table, view, procedure, etc.) touched by the commit."""

    object_type: str  # TABLE, VIEW, STORED_PROCEDURE, INDEX, SEQUENCE
    object_name: str  # DATABASE.SCHEMA.OBJECT_NAME
    action: str       # CREATED, ALTERED, DROPPED, REFERENCED
    description: str


class AffectedCodeObject(BaseModel):
    """A code object (file, class, function, endpoint) touched by the commit."""

    object_type: str  # FILE, CLASS, FUNCTION, MODULE, API_ENDPOINT
    object_name: str  # e.g. "src/models/user.py::UserModel.save()"
    action: str       # ADDED, MODIFIED, DELETED, RENAMED
    description: str


class AnalysisResult(BaseModel):
    """Structured AI analysis output for a DiffBundle."""

    # Populated from DiffBundle context
    commit_hash: str
    commit_message: str
    author: str
    timestamp: datetime
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)

    # AI-generated content
    summary: str = Field(description="Plain-English summary of what changed and why")
    impact_assessment: str = Field(description="Business/technical impact assessment")
    schema_changes: List[SchemaChange] = Field(default_factory=list)
    data_changes: List[DataChange] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    affected_db_objects: List[AffectedDatabaseObject] = Field(default_factory=list)
    affected_code_objects: List[AffectedCodeObject] = Field(default_factory=list)

    # Meta
    ai_provider: str = ""
    ai_model: str = ""
    raw_response: str = ""  # stored for debugging / audit
    parse_error: Optional[str] = None  # set if JSON parse partially failed


# ── SQL script model ──────────────────────────────────────────────────────────

class ScriptType(str, Enum):
    DDL = "DDL"
    DML = "DML"


class DMLScript(BaseModel):
    """One generated SQL file."""

    sequence: int  # 001, 002, … determines execution order
    script_type: ScriptType
    filename: str  # e.g. "001_ddl_add_user_id_column.sql"
    description: str
    sql_content: str
    table: str
    is_breaking: bool = False


class GeneratorOutput(BaseModel):
    """Aggregated output from both generators."""

    pdf_path: Optional[str] = None
    dml_scripts: List[DMLScript] = Field(default_factory=list)
    run_all_path: Optional[str] = None
    errors: List[str] = Field(default_factory=list)

    def dict_summary(self) -> Dict[str, Any]:
        return {
            "pdf": self.pdf_path,
            "dml_scripts": len(self.dml_scripts),
            "run_all": self.run_all_path,
            "errors": self.errors,
        }
