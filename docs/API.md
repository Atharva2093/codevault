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

- `repo_url` — required public Git URL
- `max_commits` — optional integer cap for commit analysis

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

- `400` if the URL is not on a supported public host
- `422` for malformed input
- `500` if analysis fails

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

This route exists as a scaffold for the future decision-analysis phase. It packages evidence and validates that AI output follows known evidence references.

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

This is not a fully shipped product feature; it is a structured foundation for future inference work.
