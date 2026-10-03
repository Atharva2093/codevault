# Project structure

This repo is organized around a small backend and supporting analysis modules.

## Top-level layout

```text
backend/
  __init__.py
  config.py
  db.py
  main.py
  ai/
    __init__.py
    evidence.py
    gemma.py
    schemas.py
  analysis/
    __init__.py
    dependency_usage.py
    git_repo.py
    manifests.py
  api/
    __init__.py
    schemas.py
    endpoints/
      __init__.py
      decisions.py
      repos.py
data/
tests/
  __init__.py
  test_dependency_usage.py
  test_phase3_decisions.py
  test_repos.py
docs/
```

## Key modules

### `backend/main.py`

FastAPI application entry point. It initializes the app and mounts the API routers.

### `backend/config.py`

Configuration and environment defaults. This includes the data directory, model config, and allowed host settings.

### `backend/db.py`

SQLite storage for sessions, commit metadata, file changes, dependency events, and future decision-analysis records.

### `backend/analysis/git_repo.py`

Git repository inspection and commit classification logic.

### `backend/analysis/manifests.py`

Dependency manifest parsing and diff extraction across supported ecosystems.

### `backend/analysis/dependency_usage.py`

Current dependency usage checks based on source imports and manifest declarations.

### `backend/api/endpoints/repos.py`

Repository ingestion and analysis endpoints.

### `backend/api/endpoints/decisions.py`

Structured scaffold for future decision analysis based on evidence.

### `backend/ai/`

Contains the model and evidence packaging layer for potential future AI reasoning.

## Testing layout

The tests focus on:

- dependency usage detection
- repository ingestion and analysis
- decision-analysis scaffolding

These are the main validation points for the current codebase.
