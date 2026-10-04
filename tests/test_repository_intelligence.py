"""Focused tests for Phase 4 deterministic repository intelligence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.ai.schemas import EvidenceReference, RepositorySynopsis
from backend.api.endpoints import repository
from backend.db import db
from backend.main import app


class FakeSynopsisClient:
    def analyze(self, evidence):
        assert evidence["repository"]["name"] == "repo"
        assert evidence["technologies"]
        assert all(item.startswith("commit:") for item in evidence["allowed_references"])
        return RepositorySynopsis(
            purpose="A repository analyzed from its local evidence.",
            what_it_does="It contains source code and tests.",
            primary_technologies=["Python"],
            major_components=["src/", "tests/"],
            project_evolution_summary="The analyzed commits show incremental changes.",
            current_state_summary="The current checkout contains the analyzed structure.",
            confidence="medium",
            uncertainty="Insufficient evidence for external usage or adoption.",
            evidence=[{
                "source_type": "commit",
                "source_id": "abc123",
                "claim": "The analyzed history contains a representative commit.",
            }],
        )


class InvalidSynopsisClient(FakeSynopsisClient):
    def analyze(self, evidence):
        synopsis = super().analyze(evidence)
        synopsis.evidence[0].source_id = "missing"
        return synopsis


class FormattedSynopsisClient(FakeSynopsisClient):
    def analyze(self, evidence):
        synopsis = super().analyze(evidence)
        synopsis.evidence[0].source_id = ' "COMMIT:ABC123" '
        return synopsis


class MultipleReferenceSynopsisClient(FakeSynopsisClient):
    def analyze(self, evidence):
        synopsis = super().analyze(evidence)
        synopsis.evidence.append(EvidenceReference(
            source_type="commit",
            source_id="abc123",
            claim="The same supplied commit is also relevant.",
        ))
        return synopsis


@pytest.fixture
def overview_repo(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    clone = tmp_path / "clones" / "session1"
    (clone / "src").mkdir(parents=True)
    (clone / "tests").mkdir()
    (clone / "src" / "main.py").write_text("print('ok')\n")
    db.create_session("session1", "https://github.com/example/repo", "example-repo", str(clone), 10)
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    db.store_commits("session1", [("session1", "abc123", "T", "t@example.com", timestamp, "Add source", "", "feature")])
    db.store_file_changes("session1", [("session1", "abc123", "src/main.py", "A", 1, 0)])
    db.set_done("session1", 1)
    monkeypatch.setattr(repository, "RepositorySynopsisClient", lambda: FakeSynopsisClient())
    return clone


def test_repository_overview_is_deterministic(overview_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["repository"] == {
        "owner": "example",
        "name": "repo",
        "url": "https://github.com/example/repo",
    }
    assert body["activity"]["unique_contributor_count"] == 1
    assert {item["name"] for item in body["technologies"]} == {"Python"}
    assert "src/" in body["structure"]
    assert body["history"][0]["sha"] == "abc123"


def test_repository_synopsis_is_validated_and_stored(overview_repo):
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
        retrieved = client.get("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200, response.text
    assert retrieved.status_code == 200
    assert response.json()["model_name"] == "gemma-4-26b-a4b-it"
    assert retrieved.json()["purpose"].startswith("A repository")
    assert db.get_repository_synopsis("session1") is not None


def test_synopsis_missing_session_is_not_created():
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/missing/synopsis")
    assert response.status_code == 404


def test_synopsis_rejects_unknown_evidence_reference(overview_repo, monkeypatch):
    monkeypatch.setattr(repository, "RepositorySynopsisClient", lambda: InvalidSynopsisClient())
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    assert response.json()["ai_status"] == "FAILED"


def test_synopsis_accepts_harmless_reference_formatting(overview_repo, monkeypatch):
    monkeypatch.setattr(repository, "RepositorySynopsisClient", lambda: FormattedSynopsisClient())
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200, response.text


def test_synopsis_accepts_multiple_valid_references(overview_repo, monkeypatch):
    monkeypatch.setattr(repository, "RepositorySynopsisClient", lambda: MultipleReferenceSynopsisClient())
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200, response.text


def test_synopsis_rejects_empty_evidence_reference(overview_repo, monkeypatch):
    class EmptyReferenceClient(FakeSynopsisClient):
        def analyze(self, evidence):
            synopsis = super().analyze(evidence)
            synopsis.evidence[0].source_id = "   "
            return synopsis

    monkeypatch.setattr(repository, "RepositorySynopsisClient", lambda: EmptyReferenceClient())
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    assert response.json()["ai_status"] == "FAILED"
