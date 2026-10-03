# Roadmap

## Completed

### Phase 1 — Repository & Git Evidence

- public repo URL validation
- Git clone and repository analysis
- commit extraction and classification
- file-change summary capture
- session persistence in SQLite

### Phase 2 — Dependency & Usage Analysis

- Dependency manifest parsing
- dependency events across versions
- current usage detection against source files
- evidence summaries in the API

## Completed

### Phase 3 — Gemma 4 Decision Extraction

- focused deterministic evidence package
- Gemma 4 structured JSON response
- Pydantic validation and evidence-reference checks
- SQLite persistence and retrieval API
- mocked provider/error/validation tests

### Phase 4 — Evidence Workspace

- responsive repository input and analysis flow
- repository overview and dependency history
- commit timeline
- decision analysis panel
- current usage, decay, ghost dependency, and counterfactual views
- FastAPI-served static demo UI

## Future

- Evidence-backed Repository Q&A
- Decision Knowledge Export
- richer exports and reporting

## Project status

The project is an early-stage hackathon MVP. The current demo combines deterministic repository evidence with optional Gemma interpretation; static analysis remains the source of truth.
