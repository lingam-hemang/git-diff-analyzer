"""Git repository access: extract diffs for a single commit or a range."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import git
from git import Commit, Diff, InvalidGitRepositoryError, Repo

from .config import AnalysisConfig
from .models import ChangeType, DiffBundle, FileDiff

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Raised for any git-related failure."""


def _open_repo(repo_path: str | Path) -> Repo:
    try:
        return Repo(str(repo_path), search_parent_directories=True)
    except (InvalidGitRepositoryError, git.exc.NoSuchPathError) as exc:
        raise GitError(f"Not a git repository: {repo_path}") from exc


def _change_type(diff: Diff) -> ChangeType:
    if diff.new_file:
        return ChangeType.ADDED
    if diff.deleted_file:
        return ChangeType.DELETED
    if diff.renamed_file:
        return ChangeType.RENAMED
    return ChangeType.MODIFIED


def _safe_diff_text(diff: Diff) -> str:
    """Decode diff bytes; fall back gracefully on encoding errors."""
    try:
        return diff.diff.decode("utf-8", errors="replace") if diff.diff else ""
    except Exception:
        return "<binary or unreadable diff>"


def _truncate_diff(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    return truncated + f"\n… [truncated — {len(text) - max_chars} chars omitted]"


def _build_file_diffs(
    diffs: list[Diff],
    cfg: AnalysisConfig,
    *,
    total_budget: int,
) -> list[FileDiff]:
    """
    Build FileDiff objects from a list of git Diff objects.

    Proportionally distributes the total_budget across files; also applies
    the per-file cap from cfg.max_file_diff_size.
    """
    if not diffs:
        return []

    per_file_budget = min(cfg.max_file_diff_size, total_budget // max(len(diffs), 1))
    file_diffs: list[FileDiff] = []

    for diff in diffs:
        path = diff.b_path or diff.a_path or "unknown"
        old_path = diff.a_path if diff.renamed_file else None
        raw_text = _safe_diff_text(diff)
        diff_text = _truncate_diff(raw_text, per_file_budget)

        additions = diff_text.count("\n+") + diff_text.count("\n+")
        deletions = diff_text.count("\n-")

        file_diffs.append(
            FileDiff(
                path=path,
                change_type=_change_type(diff),
                old_path=old_path,
                diff_text=diff_text,
                additions=max(0, additions),
                deletions=max(0, deletions),
            )
        )

    return file_diffs


def _commit_to_bundle(
    commit: Commit,
    diffs: list[Diff],
    repo_path: str,
    cfg: AnalysisConfig,
    range_label: str | None = None,
) -> DiffBundle:
    ts = datetime.fromtimestamp(commit.committed_date, tz=timezone.utc)
    file_diffs = _build_file_diffs(diffs, cfg, total_budget=cfg.max_diff_size)

    return DiffBundle(
        repo_path=repo_path,
        commit_hash=range_label or commit.hexsha,
        commit_message=commit.message.strip(),
        author=f"{commit.author.name} <{commit.author.email}>",
        timestamp=ts,
        files=file_diffs,
        total_additions=sum(f.additions for f in file_diffs),
        total_deletions=sum(f.deletions for f in file_diffs),
    )


def get_commit_diff(
    repo_path: str | Path,
    commit_ref: str = "HEAD",
    cfg: AnalysisConfig | None = None,
) -> DiffBundle:
    """
    Return a DiffBundle for a single commit.

    The diff is computed as commit vs its first parent.
    For the initial commit (no parents) the diff is computed against an empty tree.
    """
    if cfg is None:
        cfg = AnalysisConfig()

    repo = _open_repo(repo_path)

    try:
        commit: Commit = repo.commit(commit_ref)
    except git.BadName as exc:
        raise GitError(f"Unknown ref: {commit_ref!r}") from exc

    logger.debug("Analyzing commit %s (%s)", commit.hexsha[:8], commit.summary)

    if commit.parents:
        parent = commit.parents[0]
        diffs = parent.diff(commit)
    else:
        # initial commit — diff against empty tree
        empty_tree = repo.tree(repo.git.hash_object("-t", "tree", "/dev/null"))
        diffs = empty_tree.diff(commit.tree)

    return _commit_to_bundle(commit, list(diffs), str(repo_path), cfg)


def get_range_diff(
    repo_path: str | Path,
    from_ref: str,
    to_ref: str = "HEAD",
    cfg: AnalysisConfig | None = None,
) -> DiffBundle:
    """
    Return a DiffBundle representing the cumulative diff from from_ref to to_ref.

    Uses `to_commit` as the representative commit for metadata (message, author, ts).
    The range label is stored as `from_ref..to_ref`.
    """
    if cfg is None:
        cfg = AnalysisConfig()

    repo = _open_repo(repo_path)

    try:
        from_commit: Commit = repo.commit(from_ref)
        to_commit: Commit = repo.commit(to_ref)
    except git.BadName as exc:
        raise GitError(f"Unknown ref in range {from_ref!r}..{to_ref!r}: {exc}") from exc

    logger.debug(
        "Analyzing range %s..%s",
        from_commit.hexsha[:8],
        to_commit.hexsha[:8],
    )

    diffs = from_commit.diff(to_commit)
    range_label = f"{from_ref}..{to_ref}"

    return _commit_to_bundle(to_commit, list(diffs), str(repo_path), cfg, range_label)
