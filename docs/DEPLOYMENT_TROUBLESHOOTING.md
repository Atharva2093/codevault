# Deployment and troubleshooting

This project is currently a local Python backend with a SQLite data store and Git-based repository analysis. It is not a full production SaaS platform yet.

## Local deployment

Use the repo directly for local development and testing:

```bash
cd /path/to/CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Then verify:

```bash
curl http://localhost:8000/health
```

## Environment notes

This project currently expects:

- a valid Python environment
- Git installed on the system
- a writable data directory
- network access for public repo analysis

## Common issues

### 1. Git is not installed

The repository analysis logic relies on the Git CLI.

Fix:

```bash
git --version
```

If it fails, install Git for your platform.

### 2. Python version mismatch

The project targets Python 3.10+.

Fix:

```bash
python --version
```

### 3. Dependency install fails

Ensure you are inside the repository root and the virtual environment is activated.

### 4. Public repo analysis fails

The app validates public Git hosts and may reject unsupported URLs or hosts.

Review `backend/config.py` for the current allowlist and host logic.

### 5. No disk space or low resources

Repository analysis clones repos and stores metadata locally. Large repos can be expensive in constrained environments.

Mitigation:

- limit repo size where possible
- avoid running many large concurrent analyses
- use a machine with enough disk space

### 6. Test suite is slow or flaky in CI

Some tests involve public repository downloads and may be slower or more sensitive to network conditions.

Use targeted validation where needed, such as:

```bash
pytest tests/test_dependency_usage.py tests/test_phase3_decisions.py -q
```

## Operational guidance

For a lightweight local deployment, the current recommendation is to run the backend directly with Uvicorn and use the SQLite file in the data directory.

This is suitable for development, demos, and repo analysis work. It is not a production-scale multi-service deployment guide.

## Future infrastructure work

If later phases add AI reasoning or web dashboards, additional infrastructure concerns may appear, such as:

- model API credentials
- queueing or async task workers
- storage exports
- monitoring and latency tracking

Those are future concerns and are not part of the current codebase baseline.
