# Architecture

CausalCode follows one governing rule: deterministic repository facts come first; AI explains those facts later.

## End-to-End Flow

```text
Public repository URL
      |
      v
Repository session and bounded Git analysis
      |
      +--> commits, parents, authors, changed files
      +--> commit classification
      +--> manifest diffs and dependency events
      +--> current dependency usage
      +--> repository overview
      |
      v
Bounded evidence package
      |
      +--> deterministic API response
      |
      +--> optional Gemma interpretation
                |
                v
        JSON normalization and Pydantic validation
                |
                v
        evidence-reference validation and persistence
```

The user journey is:

```text
Repository Intelligence -> Project Archaeology -> Issues Intelligence -> Contributor Guidance
```

## Backend Layers

`backend/api/endpoints/repos.py` validates supported public repository URLs, creates a session, clones the repository, and stores deterministic analysis. `backend/analysis/git_repo.py` wraps the Git CLI and extracts commit metadata, parents, changed files, and commit classifications.

`backend/analysis/manifests.py` parses supported Python and JavaScript dependency manifests. `backend/analysis/dependency_usage.py` performs static import checks at the current checkout. `backend/analysis/repository_overview.py` assembles timeline, activity, contributors, technologies, structure, and representative history.

`backend/db.py` persists sessions, commits, file changes, dependency events, AI analyses, and repository synopses in SQLite. `backend/main.py` mounts the API routers and serves the vanilla frontend.

## Gemma Enrichment

`backend/ai/gemma.py` is the single Google GenAI client. The exact product model is `gemma-4-26b-a4b-it`. Requests use compact JSON evidence, bounded transport timeouts, at most two total SDK attempts, structured JSON output where required, and sanitized diagnostics.

Synopsis generation sends a minimal provider wire schema rather than the full application schema. The complete `RepositorySynopsis` model is still applied locally, followed by canonical evidence-reference validation. Other AI modules package focused evidence for decisions, archaeology, issues, and guidance; they do not ask the model to rediscover the entire repository.

## Deterministic Fallback

Synopsis enrichment is optional:

```text
Gemma succeeds -> validated AI synopsis -> ai_status=COMPLETE
Gemma fails   -> deterministic synopsis -> ai_status=FAILED
```

The fallback is assembled only from locally computed repository facts. It contains no generated evidence references and is persisted with the evidence preview and timings, so provider failure does not make repository intelligence unusable.

## Frontend Data Flow

`frontend/app.js` submits a repository URL, loads deterministic overview data, and requests optional intelligence panels. API-derived values pass through normalization helpers before rendering so missing arrays become empty arrays. The UI handles no issues, sparse history, no dependencies, unavailable Gemma enrichment, and failed optional feature requests.

## Design Constraints

- Evidence is generated deterministically before model calls.
- Returned evidence references must belong to the supplied evidence package.
- API keys never appear in responses or sanitized logs.
- Repository-specific assumptions are avoided; language, README, manifest, history, contributor count, and issue count may vary.
- Git analysis has a hard ceiling of 200 commits.
- Static dependency analysis is heuristic and cannot prove runtime-only usage.
# Architecture

CausalCode is designed around a simple rule: repository facts come first, AI interpretation comes later.

## System overview

The system currently implements a deterministic evidence pipeline:

```text
Git Repository
      |
      v
Repository / Git Analysis
      |
      +----> Commit Evidence
      |
      +----> Dependency History
      |
      +----> Current Dependency Declarations
      |
      +----> Current Usage
      |
      v
Deterministic Evidence
```

A future AI layer can consume that evidence, but the current repository does not claim that AI reasoning is complete.

```text
Deterministic Evidence
        |
        v
     Gemma 4
        |
        v
Structured Decision Analysis
```

This future AI flow is clearly marked as Phase 3 / planned.

## Current implementation

### 1. Repository and Git analysis

`backend/analysis/git_repo.py` wraps the git CLI and handles:


This is deterministic and does not depend on an LLM.

### 2. Manifest parsing and dependency diffing

`backend/analysis/manifests.py` parses supported package manifests and extracts dependency events:


It compares snapshots to detect dependencies that were added, removed, or changed.

### 3. Current dependency usage analysis

`backend/analysis/dependency_usage.py` inspects the repository at HEAD and determines whether declared dependencies are actually imported in source files.

It scans:


and returns usage counts plus file paths.

### 4. Database layer

`backend/db.py` uses SQLite to persist:


### 5. API layer

`backend/main.py` initializes the FastAPI app and mounts router modules.

The current API surfaces:


The decision-analysis route exists as a future AI scaffold, not as a complete feature.

## Data flow

The repository data flows in this order:

1. user submits a public repo URL
2. the API validates the URL and creates a session
3. the repo is cloned into a session-local directory
4. git analysis extracts commits and file changes
5. dependency diffs are collected from manifest changes
6. current usage is analyzed against HEAD
7. evidence is stored and returned in the API response

That evidence package is the foundation for any future AI interpretation.

## Design principles reflected in the code


## Future architecture

The future Phase 3 architecture would sit on top of the deterministic evidence layer and use the evidence package as the direct input to a model. The model would not replace repository facts; it would explain them in a structured, constrained way.

This is the intended extension model for later phases.
