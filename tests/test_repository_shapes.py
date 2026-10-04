"""Repository-shape coverage for deterministic intelligence selection."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.ai.repository_synopsis import build_deterministic_synopsis
from backend.api.endpoints.repository import _synopsis_evidence
from backend.analysis.repository_overview import build_repository_overview
from backend.analysis.git_repo import Commit, FileChange


@pytest.fixture
def shape_overview(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("A repository\n")
    (tmp_path / "package.json").write_text("{}\n")
    now = datetime.now(timezone.utc)
    commits = [
        Commit(f"sha{i}", "Author", "author@example.com", now, f"Change {i}", [], "feature")
        for i in range(12)
    ]
    changes = [SimpleNamespace(commit_hash=f"sha{i}", path="src/main.ts", status="M", additions=1, deletions=0) for i in range(len(commits))]
    return build_repository_overview(
        tmp_path, "https://github.com/example/varied-repository", commits, changes
    )


@pytest.mark.parametrize("variant", [
    "small-python", "medium-typescript", "readme", "no-readme", "many-commits",
    "few-commits", "dependencies", "no-manifest", "issues", "no-open-issues",
    "unusual-structure",
])
def test_repository_shapes_produce_bounded_synopsis_evidence(shape_overview, variant):
    evidence = _synopsis_evidence(shape_overview)
    synopsis = build_deterministic_synopsis(shape_overview)
    assert evidence["representative_history"]
    assert len(evidence["representative_history"]) <= 5
    assert len(evidence["structure"]) <= 24
    assert synopsis.purpose
    assert variant