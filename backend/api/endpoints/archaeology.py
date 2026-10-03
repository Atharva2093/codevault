"""Project archaeology endpoint for explaining a selected commit."""

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, status

from backend.ai.archaeology import ArchaeologyClient, build_archaeology_evidence
from backend.ai.gemma import GemmaError
from backend.ai.schemas import ProjectArchaeology
from backend.analysis.repository_overview import _branch
from backend.api.endpoints.decisions import _event_model
from backend.api.endpoints.repository import _session
from backend.api.endpoints.repository import _change_objects, _commit_objects
from backend.db import db


router = APIRouter(prefix="/api/v1/repos", tags=["archaeology"])


@router.get(
    "/{session_id}/commits/{commit_sha}/archaeology",
    response_model=ProjectArchaeology,
    status_code=status.HTTP_200_OK,
)
def explain_commit(session_id: str, commit_sha: str) -> ProjectArchaeology:
    row, clone_path = _session(session_id)
    commits = _commit_objects(session_id)
    selected = next((commit for commit in commits if commit.hash == commit_sha), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="Commit not found in analyzed repository")

    changes = _change_objects(session_id)
    events = [_event_model(event) for event in db.list_dependency_events(session_id)]
    package = build_archaeology_evidence(
        clone_path,
        row["repo_url"],
        _branch(clone_path),
        selected,
        commits,
        changes,
        events,
    )
    try:
        result = ArchaeologyClient().analyze(package.as_dict())
    except GemmaError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Gemma is not configured") from exc
        raise HTTPException(status_code=502, detail="Gemma archaeology failed") from exc

    _validate_references(result, package.allowed_references)
    return result


def _validate_references(result: ProjectArchaeology, allowed_references: list[str]) -> None:
    allowed = set(allowed_references)
    for reference in result.evidence:
        if f"{reference.source_type}:{reference.source_id}" not in allowed:
            raise HTTPException(status_code=502, detail="Gemma returned an invalid evidence reference")
