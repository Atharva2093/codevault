# CausalCode

This repository implements a deterministic, evidence-first backend for analyzing public software repositories.

## What it does

The current app can:

- validate a public repository URL
- clone a repository and inspect its Git history
- extract commit metadata and changed files
- classify commit types
- analyze dependency manifest diffs
- inspect current dependency usage at HEAD
- store evidence in SQLite and expose it through a FastAPI API

This project is intentionally focused on repository evidence generation. It is not a finished AI decision platform and does not claim full production web-product capabilities.

## Current status

The active codebase includes completed work for:

- repository ingestion
- Git-based evidence extraction
- manifest diff analysis
- dependency usage analysis
- session storage and API exposure

Planned work includes:

- Gemma-based reasoning
- structured decision extraction
- evidence-backed decision timelines
- dashboard or UI work

## Stack

- Python 3.10+
- FastAPI
- Pydantic
- SQLite + aiosqlite
- Git CLI
- pytest

## Repo layout

```text
backend/
  ai/
  analysis/
  api/
  config.py
  db.py
  main.py

data/

tests/

docs/
```

## Quick start

```bash
git clone https://github.com/<your-user>/CausalCode.git
cd CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest -q
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Verification

The repository validation baseline is:

```bash
pytest tests/test_dependency_usage.py tests/test_phase3_decisions.py -q
```

This currently passes in the project environment.

## Docs

See the docs folder for the repo-accurate project documentation:

- [GETTING_STARTED.md](./GETTING_STARTED.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [API.md](./API.md)
- [ROADMAP.md](./ROADMAP.md)
- [PRD.md](./PRD.md)
- [SETUP.md](./SETUP.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)
- [PHASE_WISE_PLAN.md](./PHASE_WISE_PLAN.md)
