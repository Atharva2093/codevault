"""Tests for the Phase 3 Gemma decision-extraction foundation."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from backend.ai.gemma import GemmaClient, GemmaError
from backend.ai.evidence import build_evidence_package
from backend.ai.schemas import DecisionAnalysis
from backend.api.endpoints import decisions
from backend.db import db
from backend.main import app


class FakeResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)


def _valid_payload():
    return {
        "decision": "Adopt requests",
        "reason": "The dependency was added for HTTP calls.",
        "evidence": [{
            "source_type": "current_usage",
            "source_id": "app.py",
            "claim": "The current source imports requests.",
        }],
        "affected_files": ["app.py"],
        "current_validity": "supported by current usage",
        "confidence": "high",
        "uncertainty": "The original issue is not recorded.",
    }


def test_valid_structured_response():
    client = FakeClient(FakeResponse(parsed=_valid_payload()))
    result = GemmaClient(
        client=client,
        api_key="test-key",
    ).analyze({"allowed_references": ["current_usage:app.py"]})
    assert result.decision == "Adopt requests"
    assert result.confidence == "high"


def test_gemma_uses_configured_model_and_structured_schema():
    client = FakeClient(FakeResponse(parsed=_valid_payload()))
    GemmaClient(client=client, api_key="test-key").analyze({})
    assert client.models.kwargs["model"] == "gemma-4-26b-a4b-it"
    config = client.models.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is DecisionAnalysis


def test_malformed_model_response():
    with pytest.raises(GemmaError):
        GemmaClient(
            client=FakeClient(FakeResponse(text="not JSON")),
            api_key="test-key",
        ).analyze({})


def test_insufficient_evidence_response_is_valid():
    payload = _valid_payload()
    payload.update({
        "decision": "insufficient evidence",
        "reason": "insufficient evidence",
        "confidence": "low",
        "uncertainty": "insufficient evidence",
    })
    result = GemmaClient(
        client=FakeClient(FakeResponse(parsed=payload)),
        api_key="test-key",
    ).analyze({})
    assert result.decision == "insufficient evidence"


def test_api_failure():
    with pytest.raises(GemmaError):
        GemmaClient(
            client=FakeClient(error=RuntimeError("provider unavailable")),
            api_key="test-key",
        ).analyze({})


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GemmaError, match="not configured"):
        GemmaClient().analyze({})


def test_confidence_validation():
    payload = _valid_payload()
    payload["confidence"] = "certain"
    with pytest.raises(ValueError):
        DecisionAnalysis.model_validate(payload)


@pytest.fixture
def phase3_repo(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    clone = tmp_path / "clones" / "session1"
    clone.mkdir(parents=True)
    (clone / "requirements.txt").write_text("requests==2.31.0\n")
    (clone / "app.py").write_text("import requests\n")
    db.create_session("session1", "https://example.com/repo", "repo", str(clone), 10)
    db.store_commits("session1", [("session1", "abc123", "T", "t@t", datetime.now(timezone.utc).isoformat(), "add requests", "", "dependency")])
    db.store_file_changes("session1", [("session1", "abc123", "app.py", "A", 1, 0)])
    db.store_dependency_events("session1", [("session1", "abc123", "requests", "python", "requirements.txt", "added", "2.31.0", None, None, None)])
    db.set_done("session1", 1)
    assert db.get_session("session1") is not None
    monkeypatch.setattr(decisions, "GemmaClient", lambda: SimpleNamespace(analyze=lambda evidence: DecisionAnalysis.model_validate(_valid_payload())))
    return clone


def test_evidence_references_and_persistence(phase3_repo):
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repos/session1/decisions/analyze",
            json={"dependency_name": "requests"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"][0]["source_id"] == "app.py"
    rows = db.list_decision_analyses("session1")
    assert len(rows) == 1
    assert rows[0]["model_name"] == "gemma-4-26b-a4b-it"
    assert json.loads(rows[0]["evidence_json"])[0]["source_id"] == "app.py"


def test_persisted_decisions_can_be_retrieved(phase3_repo):
    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/repos/session1/decisions/analyze",
            json={"dependency_name": "requests"},
        )
        response = client.get("/api/v1/repos/session1/decisions")
    assert create_response.status_code == 200
    assert response.status_code == 200
    assert response.json()[0]["model_name"] == "gemma-4-26b-a4b-it"
    assert response.json()[0]["evidence"][0]["source_id"] == "app.py"


def test_selected_commit_excludes_unrelated_dependency_events(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    commits = [
        SimpleNamespace(hash="selected", timestamp=datetime.now(timezone.utc), message="selected", change_type="dependency"),
        SimpleNamespace(hash="unrelated", timestamp=datetime.now(timezone.utc), message="unrelated", change_type="dependency"),
    ]
    changes = [
        SimpleNamespace(commit_hash="selected", path="requirements.txt", status="M", additions=1, deletions=0),
        SimpleNamespace(commit_hash="unrelated", path="other.txt", status="M", additions=1, deletions=0),
    ]
    events = [
        SimpleNamespace(
            dep_name="requests", kind="python", manifest_file="requirements.txt",
            action="added", commit_hash="selected", version=None,
            old_version=None, new_version=None,
        ),
        SimpleNamespace(
            dep_name="requests", kind="python", manifest_file="requirements.txt",
            action="changed", commit_hash="unrelated", version=None,
            old_version=None, new_version=None,
        ),
    ]

    package = build_evidence_package(
        tmp_path,
        "requests",
        events,
        commits,
        changes,
        selected_commit_hash="selected",
    )

    assert {event["commit_hash"] for event in package.dependency_events} == {"selected"}
    assert {commit["hash"] for commit in package.commits} == {"selected"}
    assert {change["commit_hash"] for change in package.file_changes} == {"selected"}
    assert all("unrelated" not in reference for reference in package.allowed_references)


def test_invalid_evidence_reference_is_rejected(phase3_repo, monkeypatch):
    payload = _valid_payload()
    payload["evidence"][0]["source_id"] = "missing.py"
    monkeypatch.setattr(decisions, "GemmaClient", lambda: SimpleNamespace(analyze=lambda evidence: DecisionAnalysis.model_validate(payload)))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/repos/session1/decisions/analyze",
            json={"dependency_name": "requests"},
        )
    assert response.status_code == 502


def test_insight_routes_use_stored_evidence(phase3_repo):
    with TestClient(app) as client:
        timeline = client.get("/api/v1/repos/session1/timeline")
        decay = client.get("/api/v1/repos/session1/dependencies/requests/decay")
        counterfactual = client.get("/api/v1/repos/session1/dependencies/requests/counterfactual")
        ghosts = client.get("/api/v1/repos/session1/dependencies/ghosts")

    assert timeline.status_code == 200
    assert timeline.json()[0]["dependency_events"][0]["dep_name"] == "requests"
    assert decay.status_code == 200
    assert decay.json()["validity"] == "supported"
    assert counterfactual.status_code == 200
    assert counterfactual.json()["likely_impact"] == "removal_requires_review"
    assert ghosts.status_code == 200
    assert ghosts.json() == []


def test_frontend_entrypoint_is_served():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Repository memory layer" in response.text