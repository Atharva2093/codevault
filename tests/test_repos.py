"""Tests for Phase 1: repository ingestion + git history evidence.

Categories:
  1. URL validation
  2. Git clone + extraction
  3. Commit classification
  4. Dependency-event extraction
  5. Malformed / empty repos
  6. Cleanup
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

# Force module imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DATA_DIR, MAX_COMMITS_HARD, PUBLIC_GIT_HOSTS
from backend.db import db
from backend.main import app
from backend.analysis.git_repo import (
    GitRepository,
    GitError,
    classify_commit,
    _is_manifest_file,
    FileChange,
    Commit,
)
from backend.analysis.manifests import (
    parse_manifest,
    diff_manifests,
    DependencyEvent,
)

client = TestClient(app)


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Each test runs in an isolated temporary directory."""
    # Make DATA_DIR point to the temp path
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    # Reset the DB singleton to use the new DATA_DIR
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    # Also patch the DATA_DIR used in repos.py and main.py
    import backend.api.endpoints.repos as repos_mod
    import backend.main as main_mod
    repos_mod.DATA_DIR = tmp_path
    main_mod.DATA_DIR = tmp_path
    yield
    # cleanup handled by tmp_path


# ── helpers ───────────────────────────────────────────────────────────────────

def _mk_repo(path: Path) -> Path:
    """Create a minimal git repository at path, commit a file."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "T"], check=True, capture_output=True)
    return path


def _commit(path: Path, filename: str, content: str, message: str):
    """Write file and commit in repo."""
    (path / filename).write_text(content)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", message], check=True, capture_output=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. URL validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestUrlValidation:
    def test_valid_github_url_accepted(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://github.com/psf/requests",
            "max_commits": 10,
        })
        assert resp.status_code in (201, 500), resp.json()

    def test_valid_github_with_dotgit(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://github.com/octocat/Hello-World.git",
            "max_commits": 5,
        })
        assert resp.status_code in (201, 500), resp.json()

    def test_gitlab_accepted(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://gitlab.com/gitlab-org/gitlab",
            "max_commits": 5,
        })
        assert resp.status_code in (201, 500), resp.json()

    def test_invalid_url_no_host(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://not-a-git-host.example.com/a/b",
            "max_commits": 5,
        })
        assert resp.status_code == 400, resp.json()

    def test_invalid_url_no_scheme(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "github.com/owner/repo",
            "max_commits": 5,
        })
        assert resp.status_code == 422, resp.json()

    def test_invalid_url_missing_slashes(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://github.com/owner",
            "max_commits": 5,
        })
        assert resp.status_code == 400, resp.json()

    def test_invalid_url_empty(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "",
            "max_commits": 5,
        })
        assert resp.status_code == 422, resp.json()

    def test_missing_max_commits_uses_default(self):
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://github.com/octocat/Hello-World",
        })
        assert resp.status_code in (201, 500), resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Git clone + extraction (real public repo)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCloneAndExtraction:
    @pytest.mark.parametrize("url", [
        "https://github.com/octocat/Hello-World",
        "https://github.com/psf/requests",
    ])
    def test_clone_and_extract_commits(self, url):
        c = TestClient(app)
        resp = c.post("/api/v1/repos", json={"repo_url": url, "max_commits": 10})
        assert resp.status_code == 201, resp.json()
        data = resp.json()
        assert data["repo_url"] == url
        assert data["status"] == "ANALYZED"
        assert data["analyzed_commits"] <= 10
        assert len(data["commits"]) > 0
        c0 = data["commits"][0]
        assert "hash" in c0
        assert "author_name" in c0
        assert "author_email" in c0
        assert "timestamp" in c0
        assert "message" in c0
        assert "change_type" in c0

    def test_max_commits_capped(self):
        c = TestClient(app)
        resp = c.post("/api/v1/repos", json={
            "repo_url": "https://github.com/psf/requests",
            "max_commits": 500,
        })
        assert resp.status_code == 201, resp.json()
        assert resp.json()["analyzed_commits"] <= 200

    def test_repo_name_extracted(self):
        c = TestClient(app)
        resp = c.post("/api/v1/repos", json={
            "repo_url": "https://github.com/psf/requests",
            "max_commits": 5,
        })
        assert resp.status_code == 201, resp.json()
        assert "requests" in resp.json()["repo_name"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Commit classification (deterministic)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCommitClassification:
    def test_dependency_via_manifest_file(self):
        assert classify_commit("updated deps", ["requirements.txt", "main.py"]) == "dependency"

    def test_dependency_via_message(self):
        assert classify_commit("bump requests to 2.28", ["README.md"]) == "dependency"

    def test_config_via_path(self):
        assert classify_commit("change config", [".github/workflows/ci.yml"]) == "config"

    def test_docs_via_path(self):
        assert classify_commit("update readme", ["README.md"]) == "docs"

    def test_refactor_via_message(self):
        assert classify_commit("refactor main module", ["src/main.py"]) == "refactor"

    def test_bugfix_via_message(self):
        assert classify_commit("fix null pointer", ["src/main.py"]) == "bugfix"

    def test_feature_via_message(self):
        assert classify_commit("feat: add new handler", ["src/handler.py"]) == "feature"

    def test_other(self):
        assert classify_commit("some work", ["src/main.py"]) == "other"

    def test_is_manifest_file(self):
        assert _is_manifest_file("requirements.txt") is True
        assert _is_manifest_file("package.json") is True
        assert _is_manifest_file("src/main.py") is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Dependency-event extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestDependencyExtraction:
    def test_requirements_added_removed(self):
        old = "flask==2.0.0\nwerkzeug\n"
        new = "flask==2.1.0\nrequests\n"
        events = diff_manifests("requirements.txt", old, new)
        names = {e.dep_name: e.action for e in events}
        assert "requests" in names and names["requests"] == "added"
        assert "werkzeug" in names and names["werkzeug"] == "removed"
        assert "flask" in names and names["flask"] == "changed"

    def test_requirements_ignores_comments_and_flags(self):
        old = "# comment\n-r other.txt\n-e git+https://example.com/dep.git\nflask\n"
        new = "flask==2.0.0\nrequests\n"
        events = diff_manifests("requirements.txt", old, new)
        names = {e.dep_name: e.action for e in events}
        assert "requests" in names and names["requests"] == "added"
        assert "flask" in names and names["flask"] == "changed"

    def test_pyproject_toml_adds_dep(self):
        old = '[project]\ndependencies = ["flask"]\n'
        new = '[project]\ndependencies = ["flask", "requests"]\n'
        events = diff_manifests("pyproject.toml", old, new)
        names = {e.dep_name: e.action for e in events}
        assert "requests" in names and names["requests"] == "added"

    def test_package_json_adds_dep(self):
        old = '{"dependencies": {"lodash": "^4.0.0"}}'
        new = '{"dependencies": {"lodash": "^4.0.0", "axios": "^1.0.0"}}'
        events = diff_manifests("package.json", old, new)
        names = {e.dep_name: e.action for e in events}
        assert "axios" in names and names["axios"] == "added"

    def test_empty_manifest(self):
        events = diff_manifests("requirements.txt", "", "")
        assert events == []

    def test_event_kind_python(self):
        events = diff_manifests("requirements.txt", "", "requests==2.0.0\n")
        assert events[0].kind == "python"

    def test_event_kind_js(self):
        events = diff_manifests("package.json", "", '{"dependencies":{"axios":"^1.0"}}')
        assert events[0].kind == "js"

    def test_changed_event_versions(self):
        events = diff_manifests("requirements.txt", "flask==2.0.0", "flask==2.1.0")
        assert events[0].action == "changed"
        assert events[0].old_version == "2.0.0"
        assert events[0].new_version == "2.1.0"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Malformed / empty repositories
# ═══════════════════════════════════════════════════════════════════════════════

class TestMalformedRepos:
    def test_malformed_commit_message(self):
        assert classify_commit("", ["main.py"]) == "other"
        assert classify_commit("🎉 update deps", ["requirements.txt"]) == "dependency"

    def test_nonexistent_manifest_in_history(self):
        events = diff_manifests("pyproject.toml", None, None)
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Cleanup
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanup:
    def test_clone_directory_removed_after_failure(self):
        # Point at an invalid repo on a valid host so clone fails; verify no clone dir left
        resp = client.post("/api/v1/repos", json={
            "repo_url": "https://github.com/causalcode-testing/non-existent-repo-12345",
            "max_commits": 5,
        })
        assert resp.status_code == 500
        import backend.config as cfg
        clones = cfg.DATA_DIR / "clones"
        assert clones.exists() is False
