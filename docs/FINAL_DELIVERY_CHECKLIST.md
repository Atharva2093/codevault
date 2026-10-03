# Final documentation checklist

Use this checklist before shipping the repository or sharing it publicly.

## Content accuracy

- [ ] The docs describe the current implementation, not aspirational product claims.
- [ ] The project is described as a deterministic evidence-analysis backend.
- [ ] AI / Gemma decision extraction is clearly marked as future work.
- [ ] The docs match the actual modules under `backend/` and `tests/`.

## Setup accuracy

- [ ] Python 3.10+ is stated as the supported version.
- [ ] Git is listed as a required runtime dependency.
- [ ] Local app startup instructions use the real FastAPI app entry point.
- [ ] Test instructions reflect the actual pytest suite.

## Scope clarity

- [ ] The docs separate current capabilities from planned features.
- [ ] No docs claim a completed dashboard, full AI product, or production SaaS platform.
- [ ] The roadmap distinguishes implemented features from future work.

## Link hygiene

- [ ] All documentation links resolve to real files in the docs folder.
- [ ] README-style references point to actual docs names.
- [ ] No references to nonexistent files remain in the docs folder.

## Final sign-off

- [ ] The docs are understandable to a new contributor.
- [ ] The docs are honest about the current maturity of the project.
- [ ] The project can be publicly shared without overstating capability.
