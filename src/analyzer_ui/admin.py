"""Django admin registration for Analysis and Script."""

from django.contrib import admin

from .models import Analysis, Script


class ScriptInline(admin.TabularInline):
    model = Script
    extra = 0
    fields = ("sequence", "script_type", "filename", "table", "is_breaking")
    readonly_fields = ("sequence", "script_type", "filename", "table", "is_breaking")
    can_delete = False
    show_change_link = True


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "commit_hash_short",
        "author",
        "timestamp",
        "analyzed_at",
        "ai_provider",
        "ai_model",
        "has_breaking_changes",
        "total_schema_changes",
        "total_data_changes",
    )
    list_filter = ("ai_provider", "ai_model")
    search_fields = ("commit_hash", "author", "commit_message", "summary")
    readonly_fields = ("id", "analyzed_at", "created_at", "has_breaking_changes")
    inlines = [ScriptInline]

    @admin.display(description="Commit")
    def commit_hash_short(self, obj: Analysis) -> str:
        return obj.commit_hash[:12]

    @admin.display(description="Breaking", boolean=True)
    def has_breaking_changes(self, obj: Analysis) -> bool:
        return obj.has_breaking_changes


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    list_display = ("filename", "script_type", "table", "sequence", "is_breaking", "analysis")
    list_filter = ("script_type", "is_breaking")
    search_fields = ("filename", "table", "description")
    readonly_fields = ("id",)
