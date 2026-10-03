# Setup guide

This repository is set up for local development with Python and FastAPI.

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
```

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

## Common setup issues

### Wrong Python version

```bash
python --version
```

Use Python 3.10 or newer.

### Dependency install fails

Make sure the venv is activated and you are running inside the repo root.

### Public repo analysis fails

CausalCode only accepts public repository URLs from a small allowlist of public Git hosts configured in `backend/config.py`.

### Gemma-based analysis fails

If `GEMINI_API_KEY` is missing, the AI decision route will not operate as a working product feature.

## Current scope

This repo is an evidence-first backend. It is excellent for deterministic repository analysis, but not a complete AI product yet.
