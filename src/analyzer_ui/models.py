"""Django models mirroring the Pydantic AnalysisResult and DMLScript."""

from __future__ import annotations

import uuid

from django.db import models


class Analysis(models.Model):
    """Persisted record of one AI analysis run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Commit metadata
    commit_hash = models.CharField(max_length=255, db_index=True)
    commit_message = models.TextField(blank=True)
    author = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)

    # AI-generated text fields
    summary = models.TextField(blank=True)
    impact_assessment = models.TextField(blank=True)

    # AI provider metadata
    ai_provider = models.CharField(max_length=100, blank=True)
    ai_model = models.CharField(max_length=255, blank=True)
    raw_response = models.TextField(blank=True)
    parse_error = models.TextField(null=True, blank=True)

    # Nested collections stored as JSON (always rendered together, never queried independently)
    schema_changes = models.JSONField(default=list)
    data_changes = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    affected_db_objects = models.JSONField(default=list)
    affected_code_objects = models.JSONField(default=list)

    # Generated file
    pdf_file = models.FileField(upload_to="analyses/pdfs/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-analyzed_at"]
        verbose_name = "Analysis"
        verbose_name_plural = "Analyses"

    def __str__(self) -> str:
        return f"{self.commit_hash[:12]} — {self.author}"

    @classmethod
    def from_pydantic(cls, result: object) -> "Analysis":
        """Create (unsaved) Analysis instance from a Pydantic AnalysisResult."""
        from git_diff_analyzer.models import AnalysisResult  # local import to avoid circular

        assert isinstance(result, AnalysisResult)
        return cls(
            commit_hash=result.commit_hash,
            commit_message=result.commit_message,
            author=result.author,
            timestamp=result.timestamp,
            analyzed_at=result.analyzed_at,
            summary=result.summary,
            impact_assessment=result.impact_assessment,
            ai_provider=result.ai_provider,
            ai_model=result.ai_model,
            raw_response=result.raw_response,
            parse_error=result.parse_error,
            schema_changes=[sc.model_dump(mode="json") for sc in result.schema_changes],
            data_changes=[dc.model_dump(mode="json") for dc in result.data_changes],
            recommendations=[r.model_dump(mode="json") for r in result.recommendations],
            affected_db_objects=[o.model_dump(mode="json") for o in result.affected_db_objects],
            affected_code_objects=[o.model_dump(mode="json") for o in result.affected_code_objects],
        )

    @property
    def has_breaking_changes(self) -> bool:
        return any(sc.get("is_breaking") for sc in self.schema_changes)

    @property
    def total_schema_changes(self) -> int:
        return len(self.schema_changes)

    @property
    def total_data_changes(self) -> int:
        return len(self.data_changes)


class Script(models.Model):
    """One generated SQL file linked to an Analysis."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    analysis = models.ForeignKey(Analysis, on_delete=models.CASCADE, related_name="scripts")

    sequence = models.PositiveIntegerField()
    script_type = models.CharField(max_length=10)  # DDL or DML
    filename = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    sql_content = models.TextField()
    table = models.CharField(max_length=255, blank=True)
    is_breaking = models.BooleanField(default=False)

    sql_file = models.FileField(upload_to="analyses/scripts/", null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        verbose_name = "Script"
        verbose_name_plural = "Scripts"

    def __str__(self) -> str:
        return self.filename

    @classmethod
    def from_pydantic(cls, dml_script: object, analysis: Analysis) -> "Script":
        """Create (unsaved) Script instance from a Pydantic DMLScript."""
        from git_diff_analyzer.models import DMLScript  # local import

        assert isinstance(dml_script, DMLScript)
        return cls(
            analysis=analysis,
            sequence=dml_script.sequence,
            script_type=dml_script.script_type.value,
            filename=dml_script.filename,
            description=dml_script.description,
            sql_content=dml_script.sql_content,
            table=dml_script.table,
            is_breaking=dml_script.is_breaking,
        )
