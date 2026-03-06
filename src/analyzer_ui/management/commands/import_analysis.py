"""Management command: import an analysis result into the database.

Two modes:
  python manage.py import_analysis --repo /path --commit HEAD --provider ollama
  python manage.py import_analysis --json /path/to/result.json
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import a git-diff analysis into the web database."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--repo", help="Path to git repository (use with --commit)")
        group.add_argument("--json", dest="json_path", help="Path to serialised AnalysisResult JSON")

        parser.add_argument("--commit", default="HEAD", help="Commit ref (default: HEAD)")
        parser.add_argument(
            "--from-ref", dest="from_ref", default=None, help="Range start ref"
        )
        parser.add_argument("--to-ref", dest="to_ref", default="HEAD", help="Range end ref")
        parser.add_argument("--provider", default=None, help="AI provider: bedrock | ollama")

    def handle(self, *args, **options):
        if options["json_path"]:
            self._import_from_json(options["json_path"])
        else:
            self._import_from_pipeline(
                repo=options["repo"],
                commit=options["commit"],
                from_ref=options["from_ref"],
                to_ref=options["to_ref"],
                provider=options["provider"],
            )

    def _import_from_json(self, json_path: str) -> None:
        from git_diff_analyzer.models import AnalysisResult

        path = Path(json_path)
        if not path.is_file():
            raise CommandError(f"File not found: {json_path}")

        raw = json.loads(path.read_text())
        result = AnalysisResult.model_validate(raw)
        self._persist(result)
        self.stdout.write(self.style.SUCCESS(f"Imported analysis for {result.commit_hash[:12]}"))

    def _import_from_pipeline(
        self,
        repo: str,
        commit: str,
        from_ref: str | None,
        to_ref: str,
        provider: str | None,
    ) -> None:
        from git_diff_analyzer.ai import get_provider
        from git_diff_analyzer.analysis import analyze
        from git_diff_analyzer.config import load_config
        from git_diff_analyzer.git_integration import get_commit_diff, get_range_diff

        cfg = load_config()

        self.stdout.write("Reading git diff…")
        if from_ref:
            bundle = get_range_diff(repo, from_ref=from_ref, to_ref=to_ref, cfg=cfg.analysis)
        else:
            bundle = get_commit_diff(repo, commit_ref=commit, cfg=cfg.analysis)

        self.stdout.write(f"Analyzing {bundle.commit_hash[:12]} with {provider or cfg.analysis.default_provider}…")
        ai_provider = get_provider(provider, cfg)
        result = analyze(bundle, ai_provider, cfg)

        self._persist(result, cfg=cfg)
        self.stdout.write(self.style.SUCCESS(f"Imported analysis for {result.commit_hash[:12]}"))

    def _persist(self, result, cfg=None) -> None:
        from git_diff_analyzer.generators.dml_generator import generate_dml_scripts
        from git_diff_analyzer.generators.pdf_generator import generate_pdf
        from git_diff_analyzer.config import load_config

        from analyzer_ui.models import Analysis, Script

        if cfg is None:
            cfg = load_config()

        analysis = Analysis.from_pydantic(result)
        analysis.save()

        # PDF
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            generate_pdf(result, tmp_path)
            short_hash = result.commit_hash.replace("..", "_").replace("/", "_")[:20]
            with open(tmp_path, "rb") as fh:
                analysis.pdf_file.save(f"analysis_{short_hash}.pdf", ContentFile(fh.read()), save=True)
            tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            self.stderr.write(f"PDF generation failed: {exc}")

        # SQL scripts
        try:
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
            self.stderr.write(f"Script generation failed: {exc}")
