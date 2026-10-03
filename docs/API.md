# API Reference

Base URL for local development: `http://localhost:8000`

## Health

### `GET /health`

Returns `{"status":"ok"}`.

## Repository Sessions

### `POST /api/v1/repos`

Clones and analyzes a public repository from a supported host.

```json
{
  "repo_url": "https://github.com/psf/requests",
  "max_commits": 25
}
```

`max_commits` is optional and capped at 200. The response contains the session ID, repository status, analyzed commits, dependency events, and dependency evidence.

### `GET /api/v1/repos/{session_id}`

Returns the stored repository session summary.

### `POST /admin/cleanup`

Local development helper that removes stored clones and resets the SQLite database.

## Repository Intelligence

### `GET /api/v1/repos/{session_id}/overview`

Returns deterministic repository identity, branch, timeline, activity, contributors, detected technologies, top-level structure, and representative history.

### `GET /api/v1/repos/{session_id}/history`

Returns the deterministic history list used by the timeline view.

### `POST /api/v1/repos/{session_id}/synopsis`

Builds a compact evidence package and requests an evidence-constrained synopsis from Gemma using `gemma-4-26b-a4b-it`. The response includes `evidence_status`, `ai_status`, `evidence_preview`, and timings.

When Gemma is unavailable, the endpoint returns HTTP 200 with a deterministic synopsis and `ai_status: "FAILED"`. This keeps repository intelligence usable without fabricating AI output.

### `GET /api/v1/repos/{session_id}/synopsis`

Returns the stored synopsis, including AI status, evidence preview, and timings.

## Project Archaeology

### `GET /api/v1/repos/{session_id}/commits/{commit_sha}/archaeology`

Packages the selected commit, related changes, dependency events, repository identity, and bounded history for Gemma. The result is validated locally and its evidence references are checked against the supplied package.

## Issues Intelligence

### `GET /api/v1/repos/{session_id}/issues`

Fetches open GitHub issues. A repository with no open issues returns an empty list.

### `GET /api/v1/repos/{session_id}/issues/{issue_number}/analysis`

Builds bounded issue evidence and returns validated issue analysis.

### `GET /api/v1/repos/{session_id}/issues/{issue_number}/guidance`

Uses stored issue analysis to return validated contributor guidance and evidence references.

## Dependency Intelligence

### `POST /api/v1/repos/{session_id}/decisions/analyze`

Analyzes a dependency, optionally narrowed to a commit:

```json
{
  "dependency_name": "requests",
  "commit_hash": "optional-commit-hash"
}
```

### `GET /api/v1/repos/{session_id}/decisions`

Returns stored dependency decision analyses.

### `GET /api/v1/repos/{session_id}/timeline`

Returns commits with dependency events grouped by commit.

### `GET /api/v1/repos/{session_id}/dependencies/ghosts`

Returns declared dependencies with no detected current source imports. This is heuristic evidence, not an automatic removal recommendation.

### `GET /api/v1/repos/{session_id}/dependencies/{dependency_name}/decay`

Compares historical dependency events with current static usage.

### `GET /api/v1/repos/{session_id}/dependencies/{dependency_name}/counterfactual`

Reports current importing files, historical events, and a cautious removal-impact assessment.

## Errors and AI Availability

Common status codes are `400` for unsupported repository URLs, `404` for missing sessions or resources, `409` when analysis is incomplete, `422` for malformed input, and `502` for failed optional AI feature requests. Synopsis is intentionally different: deterministic fallback returns `200` with `ai_status: "FAILED"` when Gemma enrichment is unavailable.

The API requires `GEMINI_API_KEY` only for Gemini-backed enrichment. It never returns the key.
# API reference

This document describes the API that actually exists in the repository today.

## Base URL

When running locally:

```text
http://localhost:8000
```

## Health check

### GET /health

Purpose: confirm the API is running.

Request:

```http
GET /health
```

Response:

```json
{
  "status": "ok"
}
```

## Repository ingestion

### POST /api/v1/repos

Purpose: validate a public Git repo URL, clone it, analyze its history, and return deterministic evidence.

Request body:

```json
{
  "repo_url": "https://github.com/psf/requests",
  "max_commits": 25
}
```

Fields:


Response:

```json
{
  "id": "session-id",
  "repo_url": "https://github.com/psf/requests",
  "repo_name": "psf-requests",
  "status": "ANALYZED",
  "created_at": "2026-01-01T12:00:00Z",
  "max_commits": 25,
  "analyzed_commits": 25,
  "commits": [
    {
      "hash": "abc123",
      "author_name": "Example Author",
      "author_email": "author@example.com",
      "timestamp": "2026-01-01T11:00:00Z",
      "message": "Update dependencies",
      "parents": ["def456"],
      "change_type": "dependency",
      "file_count": 2
    }
  ],
  "dependency_events": [
    {
      "dep_name": "requests",
      "kind": "python",
      "manifest_file": "requirements.txt",
      "action": "added",
      "version": "2.31.0",
      "commit_hash": "abc123",
      "old_version": null,
      "new_version": "2.31.0"
    }
  ],
  "dependency_evidence": [
    {
      "dependency_name": "requests",
      "ecosystem": "python",
      "manifest_file": "requirements.txt",
      "declared_version": "2.31.0",
      "current_usage_count": 2,
      "current_files": ["app.py"],
      "historical_dependency_events": [],
      "current_usage_detected": true,
      "confidence": "high"
    }
  ]
}
```

Possible errors:


## Session retrieval

### GET /api/v1/repos/{session_id}

Purpose: fetch previously stored repository analysis.

Request:

```http
GET /api/v1/repos/abc123
```

Returns the same high-level repository summary, including stored commits and dependency evidence when available.

## Admin cleanup

### POST /admin/cleanup

Purpose: remove cloned repos and reset the SQLite database during local development.

Request:

```http
POST /admin/cleanup
```

Response:

```json
{
  "cleaned": true
}
```

## Phase 3 AI decision route

### POST /api/v1/repos/{session_id}/decisions/analyze

This route packages focused deterministic evidence, sends it to Gemma 4, validates the structured response, and stores the resulting analysis.

Request body:

```json
{
  "dependency_name": "requests",
  "commit_hash": "optional-commit-hash"
}
```

Response shape:

```json
{
  "decision": "Adopt requests",
  "reason": "The dependency was added to support HTTP access.",
  "evidence": [
    {
      "source_type": "current_usage",
      "source_id": "app.py",
      "claim": "The current source imports requests."
    }
  ],
  "affected_files": ["app.py"],
  "current_validity": "supported by current usage",
  "confidence": "high",
  "uncertainty": "The original issue is not recorded."
}
```

The configured product model is `gemma-4-26b-a4b-it`. The API requires `GEMINI_API_KEY` at runtime and never exposes it in responses.

### GET /api/v1/repos/{session_id}/decisions

Returns stored decision analyses for a repository session.

### GET /api/v1/repos/{session_id}/timeline

Returns commit history with dependency events grouped by commit.

### GET /api/v1/repos/{session_id}/dependencies/ghosts

Returns declared dependencies with no detected current source imports. This is heuristic evidence, not an automatic deletion recommendation.

### GET /api/v1/repos/{session_id}/dependencies/{dependency_name}/decay

Compares historical dependency events with current usage and reports a confidence-aware validity assessment.

### GET /api/v1/repos/{session_id}/dependencies/{dependency_name}/counterfactual

Reports current importing files, historical events, and a cautious removal-impact assessment based on deterministic evidence.

## Repository synopsis

### POST /api/v1/repos/{session_id}/synopsis

Builds a bounded deterministic evidence package and asks Gemma for a structured repository synopsis. The evidence package contains repository identity, branch, timeline/activity, contributors, technologies, top-level structure, and up to eight representative commits. It does not contain source code.

The response includes `evidence_status`, `ai_status`, `evidence_preview`, and stage timings. Gemma requests use the configured `GEMMA_TIMEOUT_SECONDS` limit (60 seconds by default). A timeout returns `504` with deterministic evidence still available through the repository overview endpoint.

### GET /api/v1/repos/{session_id}/synopsis

Returns the stored synopsis when one has already been generated. Optional synopsis arrays such as `primary_technologies`, `major_components`, and `evidence` default to empty arrays.
