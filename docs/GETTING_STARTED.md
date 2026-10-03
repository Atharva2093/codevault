# Getting Started

This guide gets the current CausalCode demo running locally. For the product overview, read the repository-root [README](../README.md).

## Requirements

- Python 3.10+
- Git installed and available on PATH
- access to the internet for public repo analysis
- terminal access in the repo root

## Setup

```bash
git clone https://github.com/<your-user>/CausalCode.git
cd CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Environment variables

The repo includes an example environment file:

```bash
cp .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` if Gemma enrichment is available. The product model is fixed to `gemma-4-26b-a4b-it` by default. `.env` is ignored by Git, and VS Code is configured to load it for Python terminals.

Useful settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Runtime environment label |
| `APP_DEBUG` | `false` | Application debug flag |
| `CAUSALCODE_DATA_DIR` | `./data` | SQLite database and repository clone root |
| `GEMINI_API_KEY` | unset | Gemini API authentication for Gemma enrichment |
| `GEMMA_MODEL` | `gemma-4-26b-a4b-it` | Product model |
| `GEMMA_TIMEOUT_SECONDS` | `20` | Bounded per-request transport timeout, capped at 60 seconds |
| `GEMMA_MAX_RETRIES` | `1` | Additional SDK retry, capped so there are at most two total attempts |

## Run tests

```bash
pytest -q
```

## Start the API

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Check the health endpoint:

```bash
curl http://localhost:8000/health
```

## What the current app can do

Once the API is running, you can use it to:

- submit a public repository URL
- inspect git history and commit metadata
- review dependency manifest changes
- assess current dependency usage at HEAD
- persist and retrieve structured evidence for a session
- render repository intelligence for repositories with sparse history, no manifests, or no open issues
- request optional Gemma synopsis, archaeology, issue analysis, and contributor guidance
- return deterministic synopsis evidence when Gemma is unavailable or times out

## First workflow

1. Open `http://localhost:8000/`.
2. Enter any reasonable public GitHub, GitLab, or Bitbucket repository URL.
3. Review the deterministic overview: technologies, structure, contributors, dependencies, and history.
4. Inspect the synopsis, archaeology, issues, and contributor guidance panels.
5. Treat Gemma output as optional interpretation anchored to the displayed evidence. If it is unavailable, the deterministic repository intelligence remains usable.

The local API is also available at `http://localhost:8000`; see [API.md](API.md) for routes.
