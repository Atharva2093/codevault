"""Deterministic repository facts for the Phase 4 overview."""

import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from backend.analysis.git_repo import Commit, FileChange

LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".c": "C", ".h": "C/C++", ".cpp": "C++",
}
SKIPPED_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}


def build_repository_overview(repo_root: Path, repo_url: str, commits: list[Commit], file_changes: list[FileChange], history_limit: int = 20) -> dict:
    ordered = sorted(commits, key=lambda item: item.timestamp)
    latest_first = list(reversed(ordered))
    first = ordered[0] if ordered else None
    latest = latest_first[0] if latest_first else None
    changes_by_commit: dict[str, list[FileChange]] = {}
    for change in file_changes:
        changes_by_commit.setdefault(change.commit_hash, []).append(change)
    history = []
    for commit in latest_first[:history_limit]:
        changes = changes_by_commit.get(commit.hash, [])
        history.append({
            "reference": f"commit:{commit.hash}", "sha": commit.hash,
            "author": commit.author_name, "author_email": commit.author_email,
            "timestamp": commit.timestamp.isoformat(), "message": commit.message,
            "change_type": commit.change_type, "files": [item.path for item in changes],
            "additions": sum(item.additions for item in changes),
            "deletions": sum(item.deletions for item in changes),
        })
    contributors = {}
    for commit in ordered:
        key = commit.author_email.lower() or commit.author_name.lower()
        contributors.setdefault(key, {"name": commit.author_name, "email": commit.author_email})
    return {
        "repository": _identity(repo_url),
        "default_branch": _branch(repo_root),
        "timeline": {
            "first_commit": first.timestamp.isoformat() if first else None,
            "latest_commit": latest.timestamp.isoformat() if latest else None,
            "age_days": max(0, (latest.timestamp - first.timestamp).days) if first and latest else None,
        },
        "activity": {
            "analyzed_commit_count": len(ordered),
            "unique_contributor_count": len(contributors),
            "latest_commit_date": latest.timestamp.isoformat() if latest else None,
        },
        "contributors": sorted(contributors.values(), key=lambda item: item["name"].lower()),
        "technologies": _technologies(repo_root),
        "structure": _structure(repo_root),
        "history": history,
    }


def _identity(repo_url: str) -> dict:
    parts = [part for part in urlsplit(repo_url).path.strip("/").split("/") if part]
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    return {"owner": parts[-2] if len(parts) >= 2 else None, "name": parts[-1] if parts else "repository", "url": repo_url}


def _branch(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _technologies(repo_root: Path) -> list[dict]:
    counts: Counter[str] = Counter()
    for path in repo_root.rglob("*"):
        if path.is_file() and not _skipped(path, repo_root):
            language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
            if language:
                counts[language] += 1
    return [{"name": name, "file_count": count} for name, count in counts.most_common()]


def _structure(repo_root: Path) -> list[str]:
    return [f"{path.name}/" if path.is_dir() else path.name for path in sorted(repo_root.iterdir(), key=lambda item: item.name.lower()) if path.name != ".git" and not path.name.startswith(".")][:40]


def _skipped(path: Path, repo_root: Path) -> bool:
    return bool(SKIPPED_DIRS.intersection(path.relative_to(repo_root).parts))
