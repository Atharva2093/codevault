"""Focused tests for Phase 6 GitHub Issues Intelligence."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.ai.issues import build_issue_evidence
from backend.ai.schemas import IssueAnalysis
from backend.api.endpoints import issues
from backend.db import db
from backend.github import GitHubError, fetch_open_issues
from backend.main import app


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class FakeIssueClient:
    evidence = None
    result = None
    error = None

    def analyze(self, evidence):
        type(self).evidence = evidence
        if self.error:
            raise self.error
        return self.result


def raw_issue(number=1, body="description"):
    return {
        "number": number, "title": f"Fix parser #{number}", "body": body,
        "state": "open", "labels": [{"name": "bug"}], "user": {"login": "contributor"},
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
        "comments": 2, "html_url": f"https://github.com/example/repo/issues/{number}",
    }


def analysis_result(number=1, reference="issue:1"):
    kind, source_id = reference.split(":", 1)
    return IssueAnalysis(
        issue_number=number, summary="Parser issue", problem="The parser needs a fix.",
        likely_affected_area="parser.py", relevant_technologies=["Python"],
        estimated_complexity="medium", required_skills=["debugging"],
        facts=["The issue requests a parser fix."], reasoning=["The parser technology is present."],
        uncertainty="Insufficient evidence about the complete implementation scope.",
        evidence=[{"source_type": kind, "source_id": source_id, "claim": "The supplied issue identifies the request."}],
    )


@pytest.fixture
def issue_repo(monkeypatch, tmp_path):
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
    FakeIssueClient.result = analysis_result()
    FakeIssueClient.evidence = None
    FakeIssueClient.error = None
    monkeypatch.setattr(issues, "fetch_open_issues", lambda owner, name: [issues.GitHubIssue.model_validate({**raw_issue(), "labels": ["bug"]})])
    monkeypatch.setattr(issues, "IssueAnalysisClient", FakeIssueClient)
    return clone


def test_github_issue_parser_excludes_pull_requests_and_bounds_results(monkeypatch):
    payload = [raw_issue(index, "x" * 5000) for index in range(1, 25)]
    payload.insert(1, {**raw_issue(99), "pull_request": {"url": "https://example/pr"}})
    monkeypatch.setattr("backend.github.urlopen", lambda request, timeout: FakeResponse(payload))
    result = fetch_open_issues("example", "repo")
    assert len(result) == 20
    assert all(item.number != 99 for item in result)
    assert max(len(item.body) for item in result) == 4000
    assert result[0].labels == ["bug"]


def test_github_issue_parser_rejects_malformed_response(monkeypatch):
    monkeypatch.setattr("backend.github.urlopen", lambda request, timeout: FakeResponse({"error": "bad"}))
    with pytest.raises(GitHubError, match="invalid issue response"):
        fetch_open_issues("example", "repo")


def test_issue_metadata_schema_validation():
    issue = issues.GitHubIssue.model_validate({**raw_issue(), "labels": ["bug"]})
    assert issue.number == 1
    with pytest.raises(ValueError):
        issues.GitHubIssue.model_validate({**raw_issue(), "number": 0})


def test_deterministic_issue_evidence_is_bounded_and_has_no_history_message(tmp_path):
    issue = issues.GitHubIssue.model_validate({**raw_issue(), "labels": ["bug"]})
    commit = SimpleNamespace(hash="abc", message="unrelated", timestamp=datetime.now(timezone.utc), change_type="other")
    package = build_issue_evidence(issue, {"name": "repo", "owner": "example"}, [{"name": "Python", "file_count": 1}], [commit], [])
    assert package.package["issue"]["body"] == "description"
    assert package.package["historical_context"] == "no matching repository history found"
    assert package.allowed_references == ["issue:1", "technology:Python"]


def test_list_issues_returns_bounded_metadata(issue_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues")
    assert response.status_code == 200
    assert response.json()[0]["number"] == 1
    assert "html_url" in response.json()[0]


def test_no_open_issues_returns_empty_list(issue_repo, monkeypatch):
    monkeypatch.setattr(issues, "fetch_open_issues", lambda owner, name: [])
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues")
    assert response.status_code == 200
    assert response.json() == []


def test_valid_analysis_sends_only_supplied_evidence(issue_repo):
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/analysis")
    assert response.status_code == 200, response.text
    assert response.json()["estimated_complexity"] == "medium"
    assert FakeIssueClient.evidence["issue"]["number"] == 1
    assert len(FakeIssueClient.evidence["issue"]["body"]) <= 4000
    assert FakeIssueClient.evidence["allowed_references"] == ["issue:1", "technology:Python", "commit:abc123", "file_change:abc123:parser.py"]


def test_invalid_evidence_reference_is_rejected(issue_repo):
    FakeIssueClient.result = analysis_result(reference="issue:999")
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/analysis")
    assert response.status_code == 502


def test_unknown_issue_and_session_are_rejected(issue_repo):
    with TestClient(app) as client:
        unknown_issue = client.get("/api/v1/repos/session1/issues/99/analysis")
        unknown_session = client.get("/api/v1/repos/missing/issues")
    assert unknown_issue.status_code == 404
    assert unknown_session.status_code == 404


def test_github_failure_is_handled(issue_repo, monkeypatch):
    monkeypatch.setattr(issues, "fetch_open_issues", lambda owner, name: (_ for _ in ()).throw(GitHubError("down")))
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues")
    assert response.status_code == 502
    assert response.json()["detail"] == "GitHub issues are unavailable"


def test_gemma_failure_is_handled(issue_repo):
    from backend.ai.gemma import GemmaError
    FakeIssueClient.error = GemmaError("provider unavailable")
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/analysis")
    assert response.status_code == 502
    assert response.json()["detail"] == "Gemma issue analysis failed"


def test_insufficient_evidence_is_valid(issue_repo):
    FakeIssueClient.result = IssueAnalysis(
        issue_number=1, summary="Insufficient evidence", problem="Insufficient evidence",
        likely_affected_area="unknown", relevant_technologies=[], estimated_complexity="unknown",
        required_skills=[], facts=[], reasoning=[], uncertainty="Insufficient evidence", evidence=[],
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/repos/session1/issues/1/analysis")
    assert response.status_code == 200
    assert response.json()["estimated_complexity"] == "unknown"
    assert response.json()["uncertainty"] == "Insufficient evidence"


def test_issue_analysis_schema_rejects_invalid_complexity():
    with pytest.raises(ValueError):
        IssueAnalysis.model_validate({"issue_number": 1, "summary": "x", "problem": "x", "likely_affected_area": "x", "estimated_complexity": "certain", "uncertainty": "x"})
