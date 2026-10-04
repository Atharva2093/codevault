# CausalCode

> Git tells you what changed. CausalCode explains why it changed — and helps you decide what to contribute next.

CausalCode is an evidence-first repository intelligence tool for public Git repositories. It turns repository history, dependency changes, current usage, project structure, and GitHub issues into a guided engineering workflow:

```text
GitHub repository
  -> Repository Intelligence
  -> Project Archaeology
  -> Issues Intelligence
  -> Contributor Guidance
```

The product is repository-agnostic. Give it any reasonable public repository and it builds deterministic local evidence before requesting optional AI interpretation.

## Why It Exists

Git history is excellent at recording events, but a commit list rarely explains the engineering context behind those events. CausalCode connects historical changes to current code usage and open contribution opportunities so a developer can understand a project before changing it.

## What It Does

- Ingests a public GitHub, GitLab, or Bitbucket repository.
- Extracts commits, changed files, contributors, structure, detected technologies, and dependency events.
- Compares declared dependencies with current source usage.
- Provides a repository synopsis grounded in bounded deterministic evidence.
- Explains selected commits through Project Archaeology.
- Fetches open GitHub issues and analyzes their likely scope.
- Produces contributor guidance with suggested first steps.
- Validates AI output with Pydantic and checks every returned evidence reference.
- Falls back to deterministic repository intelligence when Gemma is unavailable or times out.

## Evidence First, AI Second

The deterministic pipeline is the product foundation:

```text
Public repository URL
  -> bounded clone and Git extraction
  -> manifest and dependency analysis
  -> current usage and repository overview
  -> focused evidence package
  -> optional Gemma interpretation
  -> local Pydantic and evidence-reference validation
```

Gemma is used through the Google Gemini API with the exact product model:

```text
gemma-4-26b-a4b-it
```

AI requests use compact evidence, structured JSON output, bounded timeouts, and at most two total SDK attempts. The application never treats generated text as repository fact: responses are normalized, validated locally, and checked against supplied evidence references. If enrichment fails, deterministic evidence remains available and the synopsis is returned with `ai_status: "FAILED"`.

## Technology Stack

- Python 3.10+
- FastAPI and Uvicorn
- Pydantic 2
- SQLite with `aiosqlite`
- Git CLI
- Google GenAI Python SDK
- Vanilla HTML, CSS, and JavaScript frontend
- pytest

## Local Setup

Requirements: Python 3.10+, Git, and network access for public repository ingestion.

```bash
git clone https://github.com/<your-user>/CausalCode.git
cd CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Set the API key in `.env` for Gemma enrichment. Never commit `.env`:

```env
APP_ENV=development
APP_DEBUG=false
CAUSALCODE_DATA_DIR=./data
GEMINI_API_KEY=your_google_api_key_here
GEMMA_MODEL=gemma-4-26b-a4b-it
GEMMA_TIMEOUT_SECONDS=20
GEMMA_MAX_RETRIES=1
```

The repository includes VS Code settings to load `.env` into Python terminals. The API also loads the root `.env` at startup when present.

## Run It

Start the backend, which also serves the frontend at `/`:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000/>. The API health check is available at:

```bash
curl http://localhost:8000/health
```

Run the minimal real Gemma production-path smoke test with an authenticated environment:

```bash
python3 run_synthetic.py
```

Run tests:

```bash
pytest -q
```

## API Workflow

1. `POST /api/v1/repos` creates a repository analysis session.
2. `GET /api/v1/repos/{session_id}/overview` returns deterministic repository facts.
3. `GET /api/v1/repos/{session_id}/history` returns analyzed commit history.
4. `POST /api/v1/repos/{session_id}/synopsis` requests optional Gemma enrichment with deterministic fallback.
5. `GET /api/v1/repos/{session_id}/synopsis` retrieves the stored synopsis.
6. `GET /api/v1/repos/{session_id}/commits/{commit_sha}/archaeology` explains a selected commit.
7. `GET /api/v1/repos/{session_id}/issues` fetches open GitHub issues.
8. `GET /api/v1/repos/{session_id}/issues/{issue_number}/analysis` analyzes an issue.
9. `GET /api/v1/repos/{session_id}/issues/{issue_number}/guidance` produces contributor guidance.
10. Dependency intelligence is available through the decisions, timeline, ghosts, decay, and counterfactual routes documented in [docs/API.md](docs/API.md).

Example repository request:

```bash
curl -X POST http://localhost:8000/api/v1/repos \
  -H 'Content-Type: application/json' \
  -d '{"repo_url":"https://github.com/psf/requests","max_commits":25}'
```

The workflow accepts arbitrary public repository URLs; no repository, language, history length, README, manifest, contributor count, or issue count is required for the deterministic overview to render.

## Current Limitations

- Repository ingestion is limited to the supported public Git hosts configured in `backend/config.py`.
- Git analysis has a hard ceiling of 200 analyzed commits.
- Language detection is suffix-based and intentionally conservative.
- Dependency usage detection is static import analysis and cannot prove runtime or configuration-only usage.
- GitHub issue intelligence requires a GitHub repository and access to the GitHub API.
- Gemma enrichment is optional and depends on Gemini API availability, model latency, quota, and the configured key.
- Large repositories can take longer to clone and analyze because deterministic extraction still reads repository metadata and supported manifests locally.

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Setup and Troubleshooting](docs/SETUP.md)
- [Project Structure](docs/PROJECT_STRUCTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Contributing](docs/CONTRIBUTING.md)

CausalCode is being developed as a hackathon-ready demonstration of evidence-grounded repository understanding: explain a project, trace its evolution, understand its issues, and identify a sensible place to contribute.