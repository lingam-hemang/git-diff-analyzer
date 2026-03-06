"""Typer CLI: analyze, config show, config init."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .ai import get_provider
from .analysis import analyze
from .config import AppConfig, load_config, write_example_config
from .generators.dml_generator import generate_dml_scripts
from .generators.pdf_generator import generate_pdf
from .generators.s3_uploader import upload_analysis_output
from .git_integration import GitError, get_commit_diff, get_range_diff
from .utils import setup_logging

app = typer.Typer(
    name="git-diff-analyzer",
    help="AI-powered git commit analysis — generates PDF docs and Snowflake SQL scripts.",
    add_completion=False,
)
config_app = typer.Typer(help="Configuration management.")
app.add_typer(config_app, name="config")

console = Console()
err_console = Console(stderr=True, style="bold red")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _abort(msg: str) -> None:
    err_console.print(f"Error: {msg}")
    raise typer.Exit(code=1)


def _resolve_output_dirs(cfg: AppConfig) -> tuple[Path, Path]:
    docs_dir = cfg.output.docs_dir
    dml_dir = cfg.output.dml_dir
    if cfg.output.create_dirs:
        docs_dir.mkdir(parents=True, exist_ok=True)
        dml_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir, dml_dir


# ── analyze command ───────────────────────────────────────────────────────────

@app.command()
def analyze_cmd(
    commit: Optional[str] = typer.Option(None, "--commit", "-c", help="Single commit ref (SHA, tag, HEAD…)"),
    from_ref: Optional[str] = typer.Option(None, "--from", help="Start of commit range"),
    to_ref: str = typer.Option("HEAD", "--to", help="End of commit range (default: HEAD)"),
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Path to git repository"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="AI provider: bedrock | ollama"),
    output_format: str = typer.Option("all", "--format", "-f", help="Output format: all | pdf | dml"),
    config_file: Optional[Path] = typer.Option(None, "--config", help="Path to config YAML"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Analyze a git commit or range and generate PDF + Snowflake SQL output."""

    setup_logging(verbose)

    cfg = load_config(config_file)
    if verbose:
        cfg.analysis.verbose = True

    # Validate provider option
    if provider and provider not in ("bedrock", "ollama"):
        _abort(f"Unknown provider {provider!r}. Use 'bedrock' or 'ollama'.")

    # Validate format
    if output_format not in ("all", "pdf", "dml"):
        _abort(f"Unknown format {output_format!r}. Use 'all', 'pdf', or 'dml'.")

    # Must specify either --commit or --from
    if commit is None and from_ref is None:
        commit = "HEAD"

    if commit and from_ref:
        _abort("Specify either --commit or --from/--to, not both.")

    # ── Get diff ──────────────────────────────────────────────────────────────
    with console.status("[bold green]Reading git diff…"):
        try:
            if commit:
                bundle = get_commit_diff(repo, commit_ref=commit, cfg=cfg.analysis)
            else:
                bundle = get_range_diff(repo, from_ref=from_ref, to_ref=to_ref, cfg=cfg.analysis)  # type: ignore[arg-type]
        except GitError as exc:
            _abort(str(exc))

    console.print(
        Panel(
            f"[bold]{bundle.commit_hash[:12]}[/bold]  {bundle.commit_message}\n"
            f"[dim]{bundle.author}  •  {bundle.timestamp.strftime('%Y-%m-%d')}[/dim]\n"
            f"[green]+{bundle.total_additions}[/green]  [red]-{bundle.total_deletions}[/red]  "
            f"({len(bundle.files)} files)",
            title="Commit",
            expand=False,
        )
    )

    # ── AI analysis ───────────────────────────────────────────────────────────
    ai_provider = get_provider(provider, cfg)  # type: ignore[arg-type]
    console.print(f"[dim]Using provider:[/dim] {ai_provider.provider_name}/{ai_provider.model_name}")

    with console.status(f"[bold green]Analyzing with {ai_provider.provider_name}…"):
        try:
            result = analyze(bundle, ai_provider, cfg)
        except Exception as exc:
            _abort(f"Analysis failed: {exc}")

    if result.parse_error:
        console.print(f"[yellow]Warning:[/yellow] {result.parse_error}")

    # ── Generate outputs ──────────────────────────────────────────────────────
    docs_dir, dml_dir = _resolve_output_dirs(cfg)
    short_hash = result.commit_hash.replace("..", "_").replace("/", "_")[:20]
    pdf_path = docs_dir / f"analysis_{short_hash}.pdf"

    outputs: list[str] = []

    if output_format in ("all", "pdf"):
        with console.status("[bold green]Generating PDF…"):
            generate_pdf(result, pdf_path)
        outputs.append(f"PDF:  {pdf_path}")

    if output_format in ("all", "dml"):
        commit_dml_dir = dml_dir / short_hash
        with console.status("[bold green]Generating SQL scripts…"):
            scripts, run_all = generate_dml_scripts(result, commit_dml_dir, cfg.snowflake)
        if scripts:
            outputs.append(f"DML:  {commit_dml_dir}/ ({len(scripts)} scripts)")
            if run_all:
                outputs.append(f"      └─ {run_all.name}")
        else:
            outputs.append("DML:  (no schema/data changes detected)")

    # ── S3 upload (aws mode) ──────────────────────────────────────────────────
    if cfg.deployment.mode == "aws" and cfg.s3.bucket:
        pdf_for_upload = pdf_path if output_format in ("all", "pdf") else None
        dml_for_upload = (commit_dml_dir if output_format in ("all", "dml") else None)  # type: ignore[possibly-undefined]
        with console.status("[bold green]Uploading to S3…"):
            try:
                s3_result = upload_analysis_output(
                    pdf_path=pdf_for_upload,
                    dml_dir=dml_for_upload,
                    bucket=cfg.s3.bucket,
                    prefix=cfg.s3.prefix,
                    commit_hash=result.commit_hash,
                    region=cfg.s3.region,
                )
                if s3_result.get("pdf_uri"):
                    outputs.append(f"S3 PDF:  {s3_result['pdf_uri']}")
                for uri in s3_result.get("dml_uris", []):
                    outputs.append(f"S3 DML:  {uri}")
                if s3_result.get("run_all_uri"):
                    outputs.append(f"S3 Run-all: {s3_result['run_all_uri']}")
            except Exception as exc:
                console.print(f"[yellow]S3 upload warning:[/yellow] {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(result.summary, title="[bold]Summary[/bold]", expand=False))

    if result.schema_changes or result.data_changes:
        tbl = Table(title="Detected Changes", show_lines=True)
        tbl.add_column("Type")
        tbl.add_column("Table")
        tbl.add_column("Operation / Change")
        tbl.add_column("Breaking")
        for sc in result.schema_changes:
            tbl.add_row(
                "[cyan]DDL[/cyan]",
                sc.table,
                sc.change_type,
                "[red]YES[/red]" if sc.is_breaking else "no",
            )
        for dc in result.data_changes:
            tbl.add_row("[yellow]DML[/yellow]", dc.table, dc.operation, "")
        console.print(tbl)

    for line in outputs:
        console.print(f"[green]✓[/green] {line}")


# ── config subcommands ────────────────────────────────────────────────────────

@config_app.command("show")
def config_show(
    config_file: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    """Show the currently active configuration."""
    cfg = load_config(config_file)
    console.print_json(cfg.model_dump_json(indent=2))


@config_app.command("init")
def config_init(
    dest: Path = typer.Option(
        Path.home() / ".git-diff-analyzer.yaml",
        "--dest",
        "-d",
        help="Where to write the config file",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
) -> None:
    """Create a starter config file at ~/.git-diff-analyzer.yaml."""
    if dest.exists() and not force:
        console.print(f"[yellow]Config already exists:[/yellow] {dest}")
        console.print("Use --force to overwrite.")
        raise typer.Exit(code=0)

    write_example_config(dest)
    console.print(f"[green]Config written to:[/green] {dest}")
    console.print("Edit it to set your AI provider credentials and Snowflake settings.")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
