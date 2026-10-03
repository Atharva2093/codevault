"""Tests for the Phase 3 Gemma decision-extraction foundation."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from backend.ai.gemma import GemmaClient, GemmaError
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

    def generate_content(self, **kwargs):
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
    result = GemmaClient(
        client=FakeClient(FakeResponse(parsed=_valid_payload())),
        api_key="test-key",
    ).analyze({"allowed_references": ["current_usage:app.py"]})
    assert result.decision == "Adopt requests"
    assert result.confidence == "high"


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