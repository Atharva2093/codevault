# Setup Guide

This repository is set up for local development with Python, FastAPI, and a static frontend served by the backend.

## Prerequisites

- Python 3.10+
- Git
- a working terminal environment
- network access for public repo analysis tests

## Clone and install

```bash
git clone https://github.com/<your-user>/CausalCode.git
cd CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Environment variables

Copy the example file:

```bash
cp .env.example .env
```

The project uses the following environment values by default:

```env
APP_ENV=development
APP_DEBUG=false
CAUSALCODE_DATA_DIR=./data
GEMINI_API_KEY=your_google_api_key_here
GEMMA_MODEL=gemma-4-26b-a4b-it
GEMMA_TIMEOUT_SECONDS=20
GEMMA_MAX_RETRIES=1
```

The real API key belongs only in the local `.env` file or the process environment. Do not put a key in `.env.example`, source code, logs, or commits. The included VS Code workspace setting enables `.env` loading for Python terminals.

## Run tests

```bash
pytest -q
```

The repo includes deterministic unit tests and some network-heavy integration tests. In constrained environments, the integration tests may fail because of Git fetch/disk limitations.

## Run the API

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

## Common Setup Issues

### Wrong Python version

```bash
python --version
```

Use Python 3.10 or newer.

### Dependency install fails

Make sure the venv is activated and you are running inside the repo root.

### Public repository analysis fails

CausalCode only accepts public repository URLs from a small allowlist of public Git hosts configured in `backend/config.py`.

### Gemma enrichment fails

If `GEMINI_API_KEY` is missing or the Gemini request times out, deterministic repository intelligence still works. Repository synopsis responses report `ai_status: "FAILED"` and retain the local evidence preview. AI-specific archaeology, issue analysis, guidance, and dependency decisions may return an API error because those features require model enrichment.

## Demo readiness

The intended demo accepts arbitrary public repositories rather than relying on a particular project, language, README, manifest, history length, contributor count, or issue count. Analysis is bounded by the configured commit ceiling and the deterministic scanners' supported file types.
