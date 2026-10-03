# Getting started

This guide covers the actual setup path for this repository.

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

## Important scope boundary

This repo is not yet a finished AI decision platform. The evidence-gathering pipeline is the key implemented capability, and any Gemma or AI-based reasoning work is future-facing rather than fully shipped.
