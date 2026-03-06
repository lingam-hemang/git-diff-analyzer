"""Views for the analyzer_ui app."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, FormView, ListView

from .forms import AnalysisForm
from .models import Analysis, Script


# ── List view ────────────────────────────────────────────────────────────────


class AnalysisListView(ListView):
    model = Analysis
    template_name = "analyzer_ui/analysis_list.html"
    context_object_name = "analyses"
    paginate_by = 20

    def get_queryset(self):
        qs = Analysis.objects.all()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(commit_hash__icontains=q) | qs.filter(
                author__icontains=q
            ) | qs.filter(commit_message__icontains=q)
        return qs.order_by("-analyzed_at")

    def get_context_data(self, **kwargs: Any) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx["search_query"] = self.request.GET.get("q", "")
        return ctx


# ── Detail view ──────────────────────────────────────────────────────────────


class AnalysisDetailView(DetailView):
    model = Analysis
    template_name = "analyzer_ui/analysis_detail.html"
    context_object_name = "analysis"

    def get_context_data(self, **kwargs: Any) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx["scripts"] = self.object.scripts.order_by("sequence")
        return ctx


# ── Create view ──────────────────────────────────────────────────────────────


class AnalysisCreateView(FormView):
    template_name = "analyzer_ui/analysis_form.html"
    form_class = AnalysisForm

    def form_valid(self, form: AnalysisForm) -> HttpResponse:
        data = form.cleaned_data
        repo_path = data["repo_path"]
        provider_name = data["provider"]
        commit = data.get("commit")
        from_ref = data.get("from_ref")
        to_ref = data.get("to_ref") or "HEAD"

        try:
            from git_diff_analyzer.ai import get_provider
            from git_diff_analyzer.analysis import analyze
            from git_diff_analyzer.config import load_config
            from git_diff_analyzer.generators.dml_generator import generate_dml_scripts
            from git_diff_analyzer.generators.pdf_generator import generate_pdf
            from git_diff_analyzer.git_integration import get_commit_diff, get_range_diff

            cfg = load_config()

            if commit:
                bundle = get_commit_diff(repo_path, commit_ref=commit, cfg=cfg.analysis)
            else:
                bundle = get_range_diff(repo_path, from_ref=from_ref, to_ref=to_ref, cfg=cfg.analysis)

            ai_provider = get_provider(provider_name, cfg)
            result = analyze(bundle, ai_provider, cfg)

        except Exception as exc:
            messages.error(self.request, f"Analysis failed: {exc}")
            return self.form_invalid(form)

        # Persist the analysis to the database
        analysis = Analysis.from_pydantic(result)
        analysis.save()

        # Generate and attach PDF
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            generate_pdf(result, tmp_path)
            short_hash = result.commit_hash.replace("..", "_").replace("/", "_")[:20]
            with open(tmp_path, "rb") as fh:
                analysis.pdf_file.save(f"analysis_{short_hash}.pdf", ContentFile(fh.read()), save=True)
            tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            messages.warning(self.request, f"PDF generation failed: {exc}")

        # Generate and attach SQL scripts
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                dml_dir = Path(tmpdir) / "dml"
                scripts_list, _ = generate_dml_scripts(result, dml_dir, cfg.snowflake)
                for dml in scripts_list:
                    script = Script.from_pydantic(dml, analysis)
                    script.save()
                    sql_path = dml_dir / dml.filename
                    if sql_path.exists():
                        with open(sql_path, "rb") as fh:
                            script.sql_file.save(dml.filename, ContentFile(fh.read()), save=True)
        except Exception as exc:
            messages.warning(self.request, f"SQL script generation failed: {exc}")

        messages.success(self.request, "Analysis completed successfully.")
        return redirect("analyzer_ui:analysis-detail", pk=analysis.pk)


# ── Download views ────────────────────────────────────────────────────────────


def download_pdf(request: HttpRequest, pk: str) -> FileResponse:
    analysis = get_object_or_404(Analysis, pk=pk)
    if not analysis.pdf_file:
        return HttpResponse("PDF not available.", status=404)
    return FileResponse(
        analysis.pdf_file.open("rb"),
        as_attachment=True,
        filename=Path(analysis.pdf_file.name).name,
        content_type="application/pdf",
    )


def download_script(request: HttpRequest, apk: str, spk: str) -> HttpResponse:
    script = get_object_or_404(Script, pk=spk, analysis_id=apk)
    return HttpResponse(
        script.sql_content,
        content_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{script.filename}"'},
    )


def download_all_scripts(request: HttpRequest, pk: str) -> FileResponse:
    analysis = get_object_or_404(Analysis, pk=pk)
    scripts = analysis.scripts.order_by("sequence")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for script in scripts:
            zf.writestr(script.filename, script.sql_content)
    buf.seek(0)

    short_hash = analysis.commit_hash[:12]
    return FileResponse(
        buf,
        as_attachment=True,
        filename=f"scripts_{short_hash}.zip",
        content_type="application/zip",
    )


def analysis_json(request: HttpRequest, pk: str) -> JsonResponse:
    analysis = get_object_or_404(Analysis, pk=pk)
    data = {
        "id": str(analysis.pk),
        "commit_hash": analysis.commit_hash,
        "commit_message": analysis.commit_message,
        "author": analysis.author,
        "timestamp": analysis.timestamp.isoformat() if analysis.timestamp else None,
        "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
        "summary": analysis.summary,
        "impact_assessment": analysis.impact_assessment,
        "ai_provider": analysis.ai_provider,
        "ai_model": analysis.ai_model,
        "schema_changes": analysis.schema_changes,
        "data_changes": analysis.data_changes,
        "recommendations": analysis.recommendations,
        "affected_db_objects": analysis.affected_db_objects,
        "affected_code_objects": analysis.affected_code_objects,
        "parse_error": analysis.parse_error,
        "scripts": [
            {
                "id": str(s.pk),
                "sequence": s.sequence,
                "script_type": s.script_type,
                "filename": s.filename,
                "description": s.description,
                "table": s.table,
                "is_breaking": s.is_breaking,
            }
            for s in analysis.scripts.order_by("sequence")
        ],
    }
    return JsonResponse(data)
