# Product Requirements Document

This document defines the current product direction for this codebase as it exists today.

## Product summary

CausalCode is a deterministic repository-analysis backend designed to answer questions about why a dependency or subsystem was introduced and how it evolved over time.

The current implementation focuses on evidence-first analysis rather than fully autonomous AI product behavior.

## Problem being solved

Developers frequently inherit repositories with unclear history, undocumented dependency rationale, and unclear reasons for code or architecture choices. The repository analysis pipeline helps surface those facts in an auditable, structured form.

## Current user value

The current product can help a user:

- inspect commit history for a public repository
- classify significant changes by type
- inspect dependency manifest diffs
- understand whether a dependency is still used
- persist evidence tied to a session

## Current scope

The implemented scope is intentionally narrow:

- public repository ingestion
- Git history mining
- manifest parsing
- dependency usage analysis
- structured evidence output

## Future scope

Later phases may add:

- AI-assisted reasoning using model outputs
- structured decision summaries
- decision timeline generation
- dependency lifecycle interpretation
- more advanced reporting and dashboards

These are future directions, not completed features in the current repo.

## User personas

### Repository maintainer

Needs to understand why a dependency or subsystem was added and whether it is still necessary.

### Engineering lead

Needs to review a dependency decision based on actual repository changes and provenance.

### Contributor

Needs a clear path to understand project history and dependency changes before making a patch.

## Requirements

### Functional requirements

1. Validate a public repository URL.
2. Clone the repository locally for analysis.
3. Extract commit metadata and file-change data.
4. Detect dependency changes from manifests.
5. Inspect current dependency usage in source files.
6. Store evidence in a local SQLite database.
7. Expose the data via a FastAPI interface.

### Non-functional requirements

- use Git as the source of truth for history
- keep evidence deterministic and inspectable
- keep AI interpretation separate from the facts layer
- make repo analysis reproducible for a given session

## Success criteria

The project succeeds when it reliably answers the question: “What evidence in this repo supports the presence and use of this dependency or module?”

That is the current core product value.
