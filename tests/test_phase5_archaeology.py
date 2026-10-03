"""Focused tests for Phase 5 project archaeology."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.ai.archaeology import build_archaeology_evidence
from backend.ai.schemas import ProjectArchaeology
from backend.api.endpoints import archaeology
from backend.ai.gemma import GemmaError
from backend.db import db
from backend.main import app


class FakeArchaeologyClient:
    evidence = None
    result = None
    error = None

    def analyze(self, evidence):
        type(self).evidence = evidence
        if self.error:
            raise self.error
        return self.result


def _result(reference="commit:abc123"):
    return ProjectArchaeology(
        what_changed="A parser dependency was added.",
        facts=["The selected commit changed package metadata."],
        likely_reason="The change likely enabled parser functionality.",
        reasoning=["The dependency event and parser file changed together."],
        uncertainty="Insufficient evidence about the original issue.",
        confidence="medium",
        evidence=[{
            "source_type": reference.split(":", 1)[0],
            "source_id": reference.split(":", 1)[1],
            "claim": "The supplied evidence identifies the selected commit.",
        }],
    )


@pytest.fixture
def archaeology_repo(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    clone = tmp_path / "clones" / "session1"
    clone.mkdir(parents=True)
    (clone / "requirements.txt").write_text("acorn==1.2.0\n")
    (clone / "parser.py").write_text("import acorn\n")
    db.create_session("session1", "https://github.com/example/repo", "repo", str(clone), 10)
    timestamp = datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    db.store_commits("session1", [
        ("session1", "abc123", "T", "t@example.com", timestamp, "Add parser support", "parent1", "feature"),
        ("session1", "nearby", "T", "t@example.com", timestamp, "Earlier parser work", "parent0", "refactor"),
    ])
    db.store_file_changes("session1", [
        ("session1", "abc123", "requirements.txt", "M", 1, 0),
        ("session1", "abc123", "parser.py", "M", 3, 1),
    ])
    db.store_dependency_events("session1", [
        ("session1", "abc123", "acorn", "python", "requirements.txt", "added", "1.2.0", None, None, None),
    ])
    db.set_done("session1", 2)
    FakeArchaeologyClient.result = _result()
    FakeArchaeologyClient.evidence = None
    FakeArchaeologyClient.error = None
    monkeypatch.setattr(archaeology, "ArchaeologyClient", FakeArchaeologyClient)
    return clone


def test_valid_archaeology_response_and_bounded_supplied_evidence(archaeology_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/commits/abc123/archaeology")
    assert response.status_code == 200, response.text
    assert response.json()["likely_reason"].startswith("The change")
    evidence = FakeArchaeologyClient.evidence
    assert evidence["target_commit"]["sha"] == "abc123"
    assert len(evidence["nearby_commits"]) <= 5
    assert len(evidence["changed_files"]) <= 50
    assert len(evidence["dependency_events"]) <= 20
    assert "source code" not in str(evidence)
    assert all(reference in evidence["allowed_references"] for reference in ["commit:abc123", "file_change:abc123:parser.py"])


def test_evidence_builder_never_sends_unbounded_history(tmp_path):
    selected = SimpleNamespace(hash="selected", author_name="T", author_email="t@t", timestamp=datetime.now(timezone.utc), message="x", change_type="other", parents=[])
    nearby = [SimpleNamespace(hash=f"commit-{index}", author_name="T", author_email="t@t", timestamp=datetime.now(timezone.utc), message="x", change_type="other", parents=[]) for index in range(20)]
    package = build_archaeology_evidence(tmp_path, "https://github.com/o/r", "main", selected, nearby, [], [])
    assert len(package.package["nearby_commits"]) == 5
    assert len(str(package.package)) < 10000


def test_invalid_evidence_reference_is_rejected(archaeology_repo):
    FakeArchaeologyClient.result = _result("commit:missing")
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/commits/abc123/archaeology")
    assert response.status_code == 502


def test_unknown_commit_and_invalid_session_are_rejected(archaeology_repo):
    with TestClient(app) as client:
        unknown = client.get("/api/v1/repos/session1/commits/missing/archaeology")
        missing = client.get("/api/v1/repos/missing/commits/abc123/archaeology")
    assert unknown.status_code == 404
    assert missing.status_code == 404


def test_gemma_failure_is_handled_cleanly(archaeology_repo):
    FakeArchaeologyClient.error = GemmaError("provider unavailable")
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/commits/abc123/archaeology")
    assert response.status_code == 502
    assert response.json()["detail"] == "Gemma archaeology failed"


def test_insufficient_evidence_is_represented(archaeology_repo):
    FakeArchaeologyClient.result = ProjectArchaeology(
        what_changed="The commit changed one file.", facts=[], likely_reason="Insufficient evidence",
        reasoning=[], uncertainty="Insufficient evidence", confidence="low", evidence=[]
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/commits/abc123/archaeology")
    assert response.status_code == 200
    assert response.json()["confidence"] == "low"
    assert response.json()["uncertainty"] == "Insufficient evidence"


def test_schema_rejects_invalid_confidence_and_missing_fields():
    with pytest.raises(ValueError):
        ProjectArchaeology.model_validate({"what_changed": "x", "likely_reason": "x", "uncertainty": "x", "confidence": "certain"})
