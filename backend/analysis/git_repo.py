"""Deterministic git history extraction using the git CLI.

All calls run with --no-pager, explicit arguments, no shell. Returns dataclasses.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

ChangeType = Literal["dependency", "refactor", "bugfix", "feature", "docs", "config", "other"]


@dataclass
class Commit:
    hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    parents: List[str]
    change_type: ChangeType


@dataclass
class FileChange:
    path: str
    status: str   # M/A/D/R/C
    additions: int
    deletions: int


class GitError(Exception):
    """Raised when a git command fails in an expected way (non-zero exit)."""
    pass


class GitRepository:
    """Thin wrapper around a local git repo on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        if not (path / ".git").exists():
            raise GitError(f"Not a git repository: {path}")

    @staticmethod
    def clone(url: str, target: Path, max_commits: int) -> "GitRepository":
        """Clone a public repo with --depth=1, then fetch full history up to max_commits."""
        target.parent.mkdir(parents=True, exist_ok=True)

        # 1. Shallow clone (fast, no history)
        # We run this in target's parent because clone creates the target directory
        _run_git(["clone", "--depth=1", "--single-branch", "--filter=blob:none", "--no-tags", url, str(target)], cwd=target.parent)

        # 2. Unshallow to get history.
        _run_git(["fetch", "--unshallow"], cwd=target)

        # 3. Verify we have a usable history
        try:
            _run_git(["rev-parse", "HEAD"], cwd=target)
        except GitError as e:
            raise GitError(f"Clone succeeded but repo is empty or broken: {e}")

        return GitRepository(target)

    def _run(self, args: List[str]) -> str:
        return _run_git(args, cwd=self.path)

    def list_commits(self, max_commits: int) -> List[Commit]:
        """Return up to max_commits commits, oldest-first (reverse topological)."""
        limit = min(max_commits, 200)  # hard ceiling from config
        fmt = "%H%n%an%n%ae%n%aI%n%s%n%P"
        raw = self._run(["log", f"--max-count={limit}", "--reverse", f"--format={fmt}"])
        return self._parse_commits(raw)

    def _parse_commits(self, raw: str) -> List[Commit]:
        commits = []
        if not raw.strip():
            return []
        parts = raw.strip().split("\n")
        # Each commit = 6 lines: hash, author_name, author_email, timestamp, subject, parents
        for i in range(0, len(parts), 6):
            if i + 5 >= len(parts):
                break
            h = parts[i].strip()
            an = parts[i + 1].strip()
            ae = parts[i + 2].strip()
            ts_str = parts[i + 3].strip()
            msg = parts[i + 4].strip()
            parents_raw = parts[i + 5].strip()
            parents = [p for p in parents_raw.split(" ") if p] if parents_raw else []

            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(timezone.utc)

            # Important: classify_commit needs the list of changed files
            changed = self._changed_files(h)
            change_type = classify_commit(msg, changed)

            commits.append(Commit(
                hash=h,
                author_name=an,
                author_email=ae,
                timestamp=ts,
                message=msg,
                parents=parents,
                change_type=change_type,
            ))
        return commits

    def _changed_files(self, commit_hash: str) -> List[str]:
        """List of file paths touched in a commit (for classification)."""
        out = self._run(["show", "--format=", "--name-only", "-r", commit_hash])
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def get_file_changes(self, commit_hash: str) -> List[FileChange]:
        """Per-file stats: path, status (M/A/D/R), additions, deletions.

        Uses --numstat with -z for NUL-safe parsing.
        """
        # --numstat -z: additions <tab> deletions <tab> path \0
        # --name-status -z: status <tab> path \0 (or status <tab> oldpath \0 newpath \0 for R/C)
        
        # Combined: --numstat --name-status -z
        raw = self._run(["show", "--format=", "--numstat", "--name-status", "-z", commit_hash])
        if not raw:
            return []
            
        parts = raw.split("\x00")
        # Git output for -z with both numstat and name-status is a bit complex.
        # It's easier to run them separately or parse carefully.
        # Let's run them separately to be safe and simple.
        
        numstat_raw = self._run(["show", "--format=", "--numstat", "-z", commit_hash])
        status_raw = self._run(["show", "--format=", "--name-status", "-z", commit_hash])
        
        stats = {} # path -> (adds, dels)
        n_parts = numstat_raw.split("\x00")
        for p in n_parts:
            if not p.strip(): continue
            # numstat entry: "adds\tdels\tpath"
            if "\t" in p:
                bits = p.split("\t")
                if len(bits) >= 3:
                    a_s, d_s, path = bits[0], bits[1], bits[2]
                    a = int(a_s) if a_s != "-" else 0
                    d = int(d_s) if d_s != "-" else 0
                    stats[path] = (a, d)

        changes = []
        s_parts = status_raw.split("\x00")
        it = iter(s_parts)
        for p in it:
            if not p.strip(): continue
            # status entry: "status\tpath" or just "status" if it's R/C followed by paths
            if "\t" in p:
                status, path = p.split("\t", 1)
            else:
                status = p
                path = next(it)
                if status.startswith(("R", "C")):
                    # Rename/Copy has TWO paths. The second one is the new name which is what numstat uses.
                    path = next(it)
            
            adds, dels = stats.get(path, (0, 0))
            changes.append(FileChange(path=path, status=status[0], additions=adds, deletions=dels))
            
        return changes

    def diff_manifest(self, parent_hash: str, head_hash: str, manifest_path: str) -> str:
        """Unified diff (unified=0) of a manifest between parent..head."""
        return self._run(["diff", "--unified=0", "--no-color", f"{parent_hash}..{head_hash}", "--", manifest_path])

    def get_manifest_content(self, commit_hash: str, manifest_path: str) -> Optional[str]:
        """Content of a manifest file at a specific commit (via git show)."""
        try:
            return self._run(["show", f"{commit_hash}:{manifest_path}"])
        except GitError:
            return None


def _run_git(args: List[str], cwd: Path) -> str:
    """Run git with --no-pager, capture stdout, raise GitError on non-zero."""
    full = ["git", "--no-pager", *args]
    try:
        res = subprocess.run(
            full,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return res.stdout
    except subprocess.CalledProcessError as e:
        msg = e.stderr.strip() or e.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed ({e.returncode}): {msg}")


# ---- commit classification ----

DEPENDENCY_KEYWORDS = {
    "dependency", "dependencies", "depend", "requirements",
    "bump", "pin", "unpin", "lock",
    "poetry", "pip", "npm", "yarn", "pnpm", "cargo", "go mod",
}

CONFIG_PATH_PATTERNS = [
    r"\.github/", r"\.gitlab-ci", r"\.gitlab/", r"Dockerfile", r"docker-compose",
    r"\.yml$", r"\.yaml$", r"\.cfg$", r"\.ini$", r"\.toml$", r"\.env",
    r"webpack", r"vite", r"tsconfig", r"babel", r"eslint", r"prettier",
    r"Makefile", r"justfile", r"\.editorconfig", r"\.dockerignore",
]

DOC_PATH_PATTERNS = [r"\.md$", r"\.rst$", r"README", r"CHANGELOG", r"docs/", r"doc/"]

REFACTOR_KEYWORDS = {"refactor", "restructure", "cleanup", "rename", "reorg", "move"}

BUGFIX_KEYWORDS = {"fix", "patch", "hotfix", "bug", "issue", "resolve", "regression"}

FEATURE_KEYWORDS = {"feat", "add", "implement", "new feature", "feature"}


def classify_commit(message: str, changed_files: List[str]) -> ChangeType:
    """Deterministic classification from message + file paths.

    Precedence: dependency (manifest changed or keyword) > config > docs > refactor > bugfix > feature > other.
    """
    msg_lower = message.lower()

    # 1. Dependency: any manifest file touched or message contains dep keywords
    for f in changed_files:
        if _is_manifest_file(f):
            return "dependency"
    if any(kw in msg_lower for kw in DEPENDENCY_KEYWORDS):
        return "dependency"

    # 2. Config/CI
    for f in changed_files:
        if any(re.search(p, f) for p in CONFIG_PATH_PATTERNS):
            return "config"

    # 3. Docs
    for f in changed_files:
        if any(re.search(p, f) for p in DOC_PATH_PATTERNS):
            return "docs"
    if "doc" in msg_lower or "readme" in msg_lower:
        return "docs"

    # 4. Refactor
    if any(kw in msg_lower for kw in REFACTOR_KEYWORDS):
        return "refactor"

    # 5. Bugfix
    if any(kw in msg_lower for kw in BUGFIX_KEYWORDS):
        return "bugfix"

    # 6. Feature
    if any(kw in msg_lower for kw in FEATURE_KEYWORDS):
        return "feature"

    return "other"


MANIFEST_FILES = {
    "requirements.txt", "requirements-dev.txt", "requirements.in",
    "pyproject.toml", "poetry.lock",
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
}


def _is_manifest_file(path: str) -> bool:
    base = os.path.basename(path)
    return base in MANIFEST_FILES