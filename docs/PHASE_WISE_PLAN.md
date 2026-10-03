# Phase-wise plan

This project is best understood as an evidence-first analysis pipeline with a future AI layer on top.

## Phase 1 — Repository and Git evidence

Implemented in the current codebase:

- public repository URL validation
- cloning and temporary repo handling
- commit enumeration and metadata extraction
- file-change summaries
- commit classification
- SQLite persistence for analysis sessions

## Phase 2 — Dependency and usage analysis

Implemented in the current codebase:

- Python and JavaScript manifest parsing
- dependency event extraction from diffed manifests
- current dependency usage detection from source imports
- API-level evidence summaries for repo analysis

## Phase 3 — AI decision extraction

This phase is planned and scaffolded, not fully implemented.

The intended direction is:

- package deterministic evidence into a structured prompt
- validate model output against the evidence set
- persist structured decisions with provenance
- separate facts from model inference

## Future phases

Possible next areas after the core evidence pipeline are:

- decision timeline analysis
- dependency lifecycle interpretation
- ghost-dependency detection
- counterfactual impact analysis
- dashboards and richer reporting

## Recommended current focus

The strongest next step is to keep improving deterministic repository evidence and documentation before expanding into AI or UX work.
