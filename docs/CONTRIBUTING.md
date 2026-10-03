# Contributing

Thank you for being interested in improving CausalCode.

## Development workflow

```bash
git clone https://github.com/<your-user>/CausalCode.git
cd CausalCode
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Keep changes focused

- stay within the repository’s current evidence-first scope
- avoid unrelated refactors in the same PR
- do not claim AI features are implemented unless they are actually in the codebase
- keep the deterministic analysis layer separate from any future model logic

## Run tests

```bash
pytest -q
```

## Commit guidance

Use short, clear commit messages that describe the change, such as:

- `fix: handle malformed manifest input`
- `docs: align project docs with current repo scope`
- `feat: support additional dependency manifest parsing`

## Pull request expectations

A good PR should:

- explain the problem being solved
- show the implementation clearly
- include or update tests when behavior changes
- remain aligned with the project’s current maturity

## Documentation expectations

Update docs whenever you change:

- API behavior
- setup instructions
- architecture assumptions
- roadmap status
- contributor expectations

## Scope boundaries

This project is intentionally limited compared with a full production product. Contributions should respect that scope and avoid mixing unrelated feature work with core repository-analysis improvements.
