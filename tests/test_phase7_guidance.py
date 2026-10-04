"""Focused tests for Phase 7 contributor guidance."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.ai.guidance import build_guidance_evidence
from backend.ai.schemas import ContributionGuidance, IssueAnalysis
from backend.api.endpoints import issues
from backend.ai.gemma import GemmaError
from backend.db import db
from backend.main import app


class FakeGuidanceClient:
    evidence = None
    result = None
    error = None

    def analyze(self, evidence):
        type(self).evidence = evidence
        if self.error:
            raise self.error
        return self.result


def valid_issue_analysis(number=1, with_history=True):
    evidence = [{
        "source_type": "issue", "source_id": str(number),
        "claim": "The issue requests a parser improvement.",
    }]
    if with_history:
        evidence.extend([
            {"source_type": "commit", "source_id": "abc123", "claim": "A parser commit is present."},
            {"source_type": "file_change", "source_id": "abc123:parser.py", "claim": "The parser file changed."},
        ])
    return IssueAnalysis(
        issue_number=number, summary="Parser improvement", problem="The parser needs an update.",
        likely_affected_area="backend/parser", relevant_technologies=["Python", "FastAPI"],
        estimated_complexity="medium", required_skills=["Python", "debugging"],
        facts=["The issue names parser behavior."], reasoning=["Parser history is relevant."],
        uncertainty="The exact implementation scope is uncertain.", evidence=evidence,
    )


def valid_guidance(number=1, history=True):
    return ContributionGuidance(
        issue_number=number, recommendation="good_starting_point", why_this_issue="It has a bounded parser scope.",
        prerequisites=["Read the parser module."], relevant_skills=["Python"],
        relevant_technologies=["FastAPI"], affected_area="backend/parser", estimated_complexity="medium",
        suggested_first_steps=["Read parser.py", "Run related tests"],
        relevant_history=["commit:abc123"] if history else [], facts=["The issue targets parser behavior."],
        reasoning=["The affected area and history are specific."], confidence="medium",
        uncertainty="The issue does not specify every edge case.", evidence=[{
            "source_type": "issue", "source_id": str(number), "claim": "The issue is supplied evidence."
        }],
    )


@pytest.fixture
def guidance_repo(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    clone = tmp_path / "clones" / "session1"
    clone.mkdir(parents=True)
    (clone / "parser.py").write_text("print('parser')\n")
    db.create_session("session1", "https://github.com/example/repo", "repo", str(clone), 10)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    db.store_commits("session1", [("session1", "abc123", "T", "t@t", timestamp, "Fix parser #1", "parent", "bugfix")])
    db.store_file_changes("session1", [("session1", "abc123", "parser.py", "M", 3, 1)])
    db.set_done("session1", 1)
    analysis = valid_issue_analysis()
    db.store_issue_analysis("session1", 1, "gemma-4-26b-a4b-it", analysis.model_dump_json())
    FakeGuidanceClient.result = valid_guidance()
    FakeGuidanceClient.evidence = None
    FakeGuidanceClient.error = None
    monkeypatch.setattr(issues, "ContributionGuidanceClient", FakeGuidanceClient)
    return clone


def test_valid_guidance_response(guidance_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 200, response.text
    assert response.json()["recommendation"] == "good_starting_point"
    assert response.json()["suggested_first_steps"]


def test_guidance_uses_existing_issue_analysis_without_refetching(guidance_repo, monkeypatch):
    monkeypatch.setattr(issues, "fetch_open_issues", lambda *args: (_ for _ in ()).throw(AssertionError("must not fetch")))
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 200
    assert FakeGuidanceClient.evidence["issue_analysis"]["issue_number"] == 1


def test_guidance_evidence_is_bounded_and_only_supplied(guidance_repo):
    analysis = valid_issue_analysis()
    evidence = build_guidance_evidence(analysis)
    assert len(evidence.package["validated_evidence"]) <= 20
    assert evidence.package["allowed_references"] == ["issue:1", "commit:abc123", "file_change:abc123:parser.py"]
    assert "repository" not in evidence.package
    with TestClient(app) as client:
        client.get("/api/v1/repos/session1/issues/1/guidance")
    assert set(FakeGuidanceClient.evidence["allowed_references"]) == set(evidence.allowed_references)


def test_invalid_evidence_reference_is_rejected(guidance_repo):
    FakeGuidanceClient.result = valid_guidance()
    FakeGuidanceClient.result.evidence[0].source_id = "999"
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 502


def test_invalid_history_reference_is_rejected(guidance_repo):
    FakeGuidanceClient.result = valid_guidance()
    FakeGuidanceClient.result.relevant_history = ["commit:missing"]
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 502


def test_unknown_session_and_issue_are_rejected(guidance_repo):
    with TestClient(app) as client:
        unknown_session = client.get("/api/v1/repos/missing/issues/1/guidance")
        unknown_issue = client.get("/api/v1/repos/session1/issues/99/guidance")
    assert unknown_session.status_code == 404
    assert unknown_issue.status_code == 404


def test_missing_issue_analysis_is_handled(guidance_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/2/guidance")
    assert response.status_code == 404
    assert response.json()["detail"] == "Issue analysis is not available"


def test_gemma_failure_is_handled(guidance_repo):
    FakeGuidanceClient.error = GemmaError("provider unavailable")
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 502
    assert response.json()["detail"] == "Gemma contribution guidance failed"


def test_insufficient_evidence_is_valid(guidance_repo):
    FakeGuidanceClient.result = ContributionGuidance(
        issue_number=1, recommendation="insufficient_evidence", why_this_issue="Insufficient evidence",
        prerequisites=[], relevant_skills=[], relevant_technologies=[], affected_area="unknown",
        estimated_complexity="unknown", suggested_first_steps=[], relevant_history=[], facts=[], reasoning=[],
        confidence="low", uncertainty="Insufficient evidence", evidence=[],
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/guidance")
    assert response.status_code == 200
    assert response.json()["recommendation"] == "insufficient_evidence"


def test_guidance_schema_validates_complexity_and_recommendation():
    with pytest.raises(ValueError):
        ContributionGuidance.model_validate({
            "issue_number": 1, "recommendation": "easy", "why_this_issue": "x",
            "affected_area": "x", "estimated_complexity": "certain", "uncertainty": "x", "confidence": "low",
        })
