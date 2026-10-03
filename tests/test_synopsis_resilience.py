"""Focused synopsis performance, contract, and failure regressions."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.ai.gemma import GemmaClient, GemmaError
from backend.ai.gemma import _normalize_json_response
from backend.ai.repository_synopsis import RepositorySynopsisClient, build_deterministic_synopsis
from backend.ai.schemas import RepositorySynopsis
from backend.api.endpoints import repository
from backend.db import db
from backend.main import app


class FakeSynopsisClient:
    evidence = None
    error = None

    def analyze(self, evidence):
        type(self).evidence = evidence
        if self.error:
            raise self.error
        return RepositorySynopsis(
            purpose="Evidence-grounded repository synopsis.",
            what_it_does="It contains source code.",
            primary_technologies=["Python"],
            major_components=["src/"],
            project_evolution_summary="The history shows incremental changes.",
            current_state_summary="The current checkout is represented by deterministic evidence.",
            confidence="medium",
            uncertainty="Insufficient evidence for external usage.",
            evidence=[],
        )


@pytest.fixture
def synopsis_repo(monkeypatch, tmp_path):
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    db.path = tmp_path / "causalcode.db"
    db.init_schema()
    clone = tmp_path / "clones" / "session1"
    (clone / "src").mkdir(parents=True)
    db.create_session("session1", "https://github.com/example/repo", "repo", str(clone), 10)
    rows = []
    changes = []
    for index in range(12):
        commit_hash = f"commit{index}"
        timestamp = datetime(2025, 1, index + 1, tzinfo=timezone.utc).isoformat()
        rows.append(("session1", commit_hash, "Author", f"a{index}@example.com", timestamp, f"Change {index}", "", "feature"))
        changes.append(("session1", commit_hash, f"src/file{index}.py", "M", 1, 0))
    db.store_commits("session1", rows)
    db.store_file_changes("session1", changes)
    db.set_done("session1", 12)
    FakeSynopsisClient.evidence = None
    FakeSynopsisClient.error = None
    monkeypatch.setattr(repository, "RepositorySynopsisClient", FakeSynopsisClient)
    return clone


def test_synopsis_evidence_is_small_and_contains_required_facts(synopsis_repo):
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    evidence = FakeSynopsisClient.evidence
    assert len(evidence["representative_history"]) == 5
    assert evidence["repository"]["name"] == "repo"
    assert set(evidence) == {"repository", "default_branch", "technologies", "structure", "representative_history", "allowed_references"}
    assert all(set(item) == {"reference", "sha", "message", "change_type", "files"} for item in evidence["representative_history"])
    assert len(str(evidence)) < 15000
    assert response.json()["evidence_status"] == "COMPLETE"
    assert response.json()["timings"]["evidence_construction_seconds"] >= 0


def test_partial_model_response_is_rejected_safely(synopsis_repo):
    class PartialClient:
        def analyze(self, evidence):
            raise GemmaError("Gemma returned an empty response")

    repository.RepositorySynopsisClient = PartialClient
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    assert response.json()["ai_status"] == "FAILED"
    assert response.json()["evidence_status"] == "COMPLETE"


def test_gemma_timeout_returns_clean_error_with_evidence_available(synopsis_repo):
    FakeSynopsisClient.error = GemmaError("Gemma analysis timed out")
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    assert response.json()["ai_status"] == "FAILED"
    assert "deterministic" in response.json()["current_state_summary"]
    assert response.json()["evidence"] == []


def test_failed_synopsis_is_persisted_with_evidence_preview(synopsis_repo):
    FakeSynopsisClient.error = GemmaError("Gemma provider returned HTTP 504")
    with TestClient(app) as client:
        response = client.post("/api/v1/repos/session1/synopsis")
        retrieved = client.get("/api/v1/repos/session1/synopsis")
    assert response.status_code == 200
    assert retrieved.status_code == 200
    assert retrieved.json()["ai_status"] == "FAILED"
    assert retrieved.json()["evidence_preview"]["repository"]["name"] == "repo"


def test_deterministic_synopsis_has_no_generated_evidence():
    result = build_deterministic_synopsis({
        "repository": {"name": "sample"},
        "technologies": [{"name": "Python"}],
        "structure": ["src/"],
        "history": [{"message": "Add parser"}],
    })
    assert result.confidence == "low"
    assert result.evidence == []


def test_optional_synopsis_arrays_have_schema_defaults():
    result = RepositorySynopsis.model_validate({
        "purpose": "x", "what_it_does": "x", "project_evolution_summary": "x",
        "current_state_summary": "x", "confidence": "low", "uncertainty": "Insufficient evidence",
    })
    assert result.primary_technologies == []
    assert result.major_components == []
    assert result.evidence == []


def test_gemma_partial_json_is_wrapped_as_gemma_error():
    class Response:
        parsed = None
        text = '{"purpose":"x"}'

    class Models:
        def generate_content(self, **kwargs):
            return Response()

    with pytest.raises(GemmaError):
        RepositorySynopsisClient(client=SimpleNamespace(models=Models()), api_key="test").analyze({})


@pytest.mark.parametrize("text", [
    '{"purpose":"x"}',
    '```json\n{"purpose":"x"}\n```',
    '```JSON\n{"purpose":"x"}\n```',
    '  \n```json\n{"purpose":"x"}\n```  \n',
])
def test_json_response_normalizes_only_supported_fences(text):
    assert _normalize_json_response(text) == '{"purpose":"x"}'


def test_malformed_json_remains_invalid():
    with pytest.raises(ValueError):
        RepositorySynopsis.model_validate_json(_normalize_json_response('```json\n{"purpose":}\n```'))


def test_json_followed_by_arbitrary_text_remains_invalid():
    with pytest.raises(ValueError):
        RepositorySynopsis.model_validate_json(_normalize_json_response('{"purpose":"x"} trailing'))


def test_plain_json_response_is_validated():
    class Response:
        parsed = None
        text = '{"purpose":"x","what_it_does":"x","project_evolution_summary":"x","current_state_summary":"x","confidence":"low","uncertainty":"x","evidence":[]}'

    result = RepositorySynopsisClient(client=SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kwargs: Response()
    )), api_key="test").analyze({})
    assert result.purpose == "x"


def test_synopsis_uses_minimal_wire_schema_and_local_full_validation():
    captured = {}

    class Response:
        parsed = None
        text = '{"purpose":"x","what_it_does":"x","project_evolution_summary":"x","current_state_summary":"x","confidence":"low","uncertainty":"x","evidence":[]}'

    def generate_content(**kwargs):
        captured.update(kwargs)
        return Response()

    result = RepositorySynopsisClient(client=SimpleNamespace(models=SimpleNamespace(
        generate_content=generate_content
    )), api_key="test").analyze({"repository": {"name": "r"}})
    assert result is not None
    wire_schema = captured["config"].response_schema
    assert wire_schema["type"] == "object"
    assert "minLength" not in str(wire_schema)
    assert "RepositorySynopsis" not in str(wire_schema)


def test_fenced_json_response_is_validated():
    class Response:
        parsed = None
        text = '```json\n{"purpose":"x","what_it_does":"x","project_evolution_summary":"x","current_state_summary":"x","confidence":"low","uncertainty":"x","evidence":[]}\n```'

    result = RepositorySynopsisClient(client=SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kwargs: Response()
    )), api_key="test").analyze({})
    assert result.purpose == "x"


def test_response_validation_error_identifies_response_boundary():
    class Response:
        parsed = None
        text = '{"purpose":"x"}'

    with pytest.raises(GemmaError, match="response JSON validation failed: fields="):
        RepositorySynopsisClient(client=SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: Response()
        )), api_key="test").analyze({})


def test_sdk_config_validation_error_identifies_config_boundary(monkeypatch):
    import google.genai.types

    class InvalidConfig:
        def __init__(self, **kwargs):
            raise ValueError("invalid config")

    monkeypatch.setattr(google.genai.types, "GenerateContentConfig", InvalidConfig)
    with pytest.raises(GemmaError, match="Gemma request failed: ValueError"):
        GemmaClient(client=SimpleNamespace(models=SimpleNamespace()), api_key="test").analyze({})


def test_fabricated_evidence_reference_is_rejected():
    class Response:
        parsed = {
            "purpose": "x", "what_it_does": "x", "project_evolution_summary": "x",
            "current_state_summary": "x", "confidence": "low", "uncertainty": "x",
            "evidence": [{"source_type": "commit", "source_id": "fabricated", "claim": "x"}],
        }
        text = None

    synopsis = RepositorySynopsisClient(client=SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **kwargs: Response()
    )), api_key="test").analyze({})
    with pytest.raises(GemmaError):
        repository._validate_synopsis_evidence(synopsis, {"allowed_references": ["commit:abc123"]})


@pytest.mark.parametrize("error, message", [
    (TimeoutError("timed out"), "timed out"),
    (ConnectionError("connection failed"), "network request failed"),
])
def test_provider_failures_are_sanitized(error, message):
    class Models:
        def generate_content(self, **kwargs):
            raise error

    with pytest.raises(GemmaError, match=message):
        GemmaClient(client=SimpleNamespace(models=Models()), api_key="test").analyze({})


@pytest.mark.parametrize("status", [500, 429])
def test_http_provider_failures_are_sanitized(status):
    class ProviderError(Exception):
        status_code = status

    class Models:
        def generate_content(self, **kwargs):
            raise ProviderError("provider failure")

    with pytest.raises(GemmaError, match=f"HTTP {status}"):
        GemmaClient(client=SimpleNamespace(models=Models()), api_key="test").analyze({})


def test_provider_deadline_is_classified_explicitly():
    class ProviderError(Exception):
        status_code = 504
        code = 504

    class Models:
        def generate_content(self, **kwargs):
            raise ProviderError("DEADLINE_EXCEEDED")

    with pytest.raises(GemmaError, match="timed out: provider deadline exceeded"):
        GemmaClient(client=SimpleNamespace(models=Models()), api_key="test").analyze({})


def test_sdk_retry_count_is_bounded(monkeypatch):
    import backend.ai.gemma as gemma

    captured = {}

    class RetryOptions:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.__dict__.update(kwargs)

    class HttpOptions:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class GenAI:
        class Client:
            def __init__(self, **kwargs):
                captured.update(kwargs)

    monkeypatch.setattr(gemma, "GEMMA_MAX_RETRIES", 2)
    monkeypatch.setattr("google.genai.types.HttpRetryOptions", RetryOptions)
    monkeypatch.setattr("google.genai.types.HttpOptions", HttpOptions)
    monkeypatch.setattr("google.genai.Client", GenAI.Client)
    client = GemmaClient(api_key="test")._build_client()
    assert client is not None
    assert captured["retry_options"].attempts == 3


def test_sdk_retry_policy_allows_one_short_retry(monkeypatch):
    import backend.ai.gemma as gemma

    captured = {}

    class RetryOptions:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HttpOptions:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class GenAI:
        class Client:
            def __init__(self, **kwargs):
                captured.update(kwargs)

    monkeypatch.setattr(gemma, "GEMMA_MAX_RETRIES", 1)
    monkeypatch.setattr(gemma, "GEMMA_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr("google.genai.types.HttpRetryOptions", RetryOptions)
    monkeypatch.setattr("google.genai.types.HttpOptions", HttpOptions)
    monkeypatch.setattr("google.genai.Client", GenAI.Client)
    GemmaClient(api_key="test")._build_client()
    options = captured["retry_options"]
    assert options.attempts == 2
    assert options.initial_delay == 0.5
    assert options.max_delay == 1.5
    assert options.http_status_codes == [429, 500, 503, 504]
    assert captured["timeout"] == 20000
