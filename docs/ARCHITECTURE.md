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

- repository cloning
- commit enumeration
- parent/author metadata extraction
- file-change capture
- commit classification by message and touched files

This is deterministic and does not depend on an LLM.

### 2. Manifest parsing and dependency diffing

`backend/analysis/manifests.py` parses supported package manifests and extracts dependency events:

- requirements and pyproject for Python
- package.json for JavaScript
- lightweight handling for lockfile-like formats

It compares snapshots to detect dependencies that were added, removed, or changed.

### 3. Current dependency usage analysis

`backend/analysis/dependency_usage.py` inspects the repository at HEAD and determines whether declared dependencies are actually imported in source files.

It scans:

- Python imports
- JavaScript/TypeScript imports
- supported manifest files

and returns usage counts plus file paths.

### 4. Database layer

`backend/db.py` uses SQLite to persist:

- sessions
- commits
- file changes
- dependency events
- decision-analysis records for the Phase 3 scaffold

### 5. API layer

`backend/main.py` initializes the FastAPI app and mounts router modules.

The current API surfaces:

- health checks
- repository ingestion
- session retrieval
- cleanup helper

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

- deterministic analysis before AI reasoning
- evidence-first reasoning
- repository-local evidence only
- testability through isolated fixtures
- separation of analysis concerns across git, manifest, usage, and API layers

## Future architecture

The future Phase 3 architecture would sit on top of the deterministic evidence layer and use the evidence package as the direct input to a model. The model would not replace repository facts; it would explain them in a structured, constrained way.

This is the intended extension model for later phases.
