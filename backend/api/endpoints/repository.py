"""Repository intelligence overview and synopsis endpoints."""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, status

from backend.ai.gemma import GemmaError
from backend.ai.repository_synopsis import RepositorySynopsisClient
from backend.ai.schemas import RepositorySynopsis
from backend.analysis.repository_overview import build_repository_overview
from backend.api.schemas import RepositorySynopsisResponse
from backend.config import GEMMA_MODEL
from backend.db import db


router = APIRouter(prefix="/api/v1/repos", tags=["repository-intelligence"])


def _session(session_id: str):
    row = db.get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    if row["status"] != "ANALYZED":
        raise HTTPException(status_code=409, detail="Repository analysis is not complete")
    clone_path = Path(row["clone_path"])
    if not clone_path.exists():
        raise HTTPException(status_code=409, detail="Repository clone is unavailable")
    return row, clone_path


def _commit_objects(session_id: str) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            hash=row["commit_hash"],
            author_name=row["author_name"] or "Unknown",
            author_email=row["author_email"] or "",
            timestamp=datetime.fromisoformat(row["timestamp"]),
            message=row["message"] or "",
            parents=row["parent_hashes"].split() if row["parent_hashes"] else [],
            change_type=row["change_type"] or "other",
        )
        for row in db.list_commits(session_id)
    ]


def _change_objects(session_id: str) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            commit_hash=row["commit_hash"],
            path=row["path"],
            status=row["status"],
            additions=row["additions"],
            deletions=row["deletions"],
        )
        for row in db.list_file_changes(session_id)
    ]


def _synopsis_evidence(overview: dict) -> dict:
    return {
        "repository": overview["repository"],
        "default_branch": overview["default_branch"],
        "timeline": overview["timeline"],
        "activity": overview["activity"],
        "contributors": overview["contributors"],
        "technologies": overview["technologies"],
        "structure": overview["structure"],
        "representative_history": overview["history"][:12],
        "allowed_references": [
            entry["reference"] for entry in overview["history"]
        ],
    }


def _validate_synopsis_evidence(synopsis: RepositorySynopsis, evidence: dict) -> None:
    allowed = set(evidence["allowed_references"])
    for reference in synopsis.evidence:
        if reference.source_type != "commit" or f"commit:{reference.source_id}" not in allowed:
            raise GemmaError("Gemma returned an invalid synopsis evidence reference")


def _stored_synopsis(row) -> RepositorySynopsisResponse:
    values = json.loads(row["synopsis_json"])
    return RepositorySynopsisResponse(
        **values,
        session_id=row["session_id"],
        model_name=row["model_name"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


@router.get("/{session_id}/overview")
def get_repository_overview(session_id: str) -> dict:
    row, clone_path = _session(session_id)
    return build_repository_overview(
        clone_path,
        row["repo_url"],
        _commit_objects(session_id),
        _change_objects(session_id),
    )


@router.get("/{session_id}/history")
def get_repository_history(session_id: str) -> list[dict]:
    return get_repository_overview(session_id)["history"]


@router.post(
    "/{session_id}/synopsis",
    response_model=RepositorySynopsisResponse,
    status_code=status.HTTP_200_OK,
)
def create_repository_synopsis(session_id: str) -> RepositorySynopsisResponse:
    row, clone_path = _session(session_id)
    overview = build_repository_overview(
        clone_path,
        row["repo_url"],
        _commit_objects(session_id),
        _change_objects(session_id),
    )
    try:
        synopsis = RepositorySynopsisClient().analyze(_synopsis_evidence(overview))
        _validate_synopsis_evidence(synopsis, _synopsis_evidence(overview))
    except GemmaError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Gemma is not configured") from exc
        raise HTTPException(status_code=502, detail="Gemma synopsis failed") from exc
    db.store_repository_synopsis(
        session_id,
        GEMMA_MODEL,
        json.dumps(synopsis.model_dump()),
    )
    return _stored_synopsis(db.get_repository_synopsis(session_id))


@router.get(
    "/{session_id}/synopsis",
    response_model=RepositorySynopsisResponse,
    status_code=status.HTTP_200_OK,
)
def get_repository_synopsis(session_id: str) -> RepositorySynopsisResponse:
    _session(session_id)
    row = db.get_repository_synopsis(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Repository synopsis not generated")
    return _stored_synopsis(row)
