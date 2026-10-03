"""Repository intelligence overview and synopsis endpoints."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, status

from backend.ai.gemma import GemmaError
from backend.ai.repository_synopsis import RepositorySynopsisClient, build_deterministic_synopsis
from backend.ai.schemas import RepositorySynopsis
from backend.analysis.repository_overview import build_repository_overview
from backend.api.schemas import RepositorySynopsisResponse
from backend.config import GEMMA_MODEL
from backend.db import db


router = APIRouter(prefix="/api/v1/repos", tags=["repository-intelligence"])
logger = logging.getLogger(__name__)


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
    history = []
    for entry in overview["history"][:5]:
        history.append({
            "reference": entry["reference"],
            "sha": entry["sha"],
            "message": entry["message"][:240],
            "change_type": entry["change_type"],
            "files": entry.get("files", [])[:5],
        })
    return {
        "repository": overview["repository"],
        "default_branch": overview["default_branch"],
        "technologies": [
            {"name": item["name"], "file_count": item["file_count"]}
            for item in overview["technologies"][:12]
        ],
        "structure": overview["structure"][:24],
        "representative_history": history,
        "allowed_references": [entry["reference"] for entry in history],
    }


def _synopsis_preview(overview: dict) -> dict:
    timeline = overview.get("timeline", {})
    activity = overview.get("activity", {})
    history = overview.get("history", [])[:8]
    return {
        "repository": overview.get("repository", {}),
        "technologies": [item.get("name") for item in overview.get("technologies", [])[:20]],
        "commits_examined": activity.get("analyzed_commit_count", 0),
        "contributors": activity.get("unique_contributor_count", 0),
        "first_commit": timeline.get("first_commit"),
        "latest_commit": timeline.get("latest_commit"),
        "representative_commits": [
            {"sha": item.get("sha"), "message": item.get("message")}
            for item in history
        ],
    }


def _validate_synopsis_evidence(synopsis: RepositorySynopsis, evidence: dict) -> None:
    allowed = {_normalize_synopsis_reference(item) for item in evidence["allowed_references"]}
    returned = []
    rejected = 0
    for reference in synopsis.evidence:
        normalized_id = _normalize_synopsis_reference(reference.source_id)
        candidate = normalized_id if normalized_id.startswith("commit:") else _normalize_synopsis_reference(
            f"{reference.source_type}:{normalized_id}"
        )
        returned.append(candidate)
        if reference.source_type != "commit" or candidate not in allowed:
            rejected += 1
            logger.warning(
                "synopsis evidence reference rejected returned=%s allowed_count=%d",
                candidate, len(allowed),
            )
            raise GemmaError("Gemma returned an invalid synopsis evidence reference")
    logger.info(
        "synopsis evidence references returned_count=%d accepted_count=%d rejected_count=%d refs=%s",
        len(returned), len(returned) - rejected, rejected, returned,
    )


def _normalize_synopsis_reference(reference: str) -> str:
    """Normalize representation only; membership remains restricted to supplied refs."""
    value = str(reference).strip()
    for _ in range(2):
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1].strip()
    if value.lower().startswith("commit:"):
        value = f"commit:{value.split(':', 1)[1].strip()}"
    return value.lower()


def _stored_synopsis(row) -> RepositorySynopsisResponse:
    values = json.loads(row["synopsis_json"])
    ai_status = values.pop("ai_status", "COMPLETE")
    evidence_preview = values.pop("evidence_preview", {})
    timings = values.pop("timings", {})
    return RepositorySynopsisResponse(
        **values,
        session_id=row["session_id"],
        model_name=row["model_name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        ai_status=ai_status,
        evidence_preview=evidence_preview,
        timings=timings,
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
    evidence_started = time.perf_counter()
    overview = build_repository_overview(
        clone_path,
        row["repo_url"],
        _commit_objects(session_id),
        _change_objects(session_id),
    )
    evidence = _synopsis_evidence(overview)
    evidence_seconds = time.perf_counter() - evidence_started
    logger.info(
        "synopsis evidence session=%s seconds=%.3f bytes=%d commits=%d",
        session_id, evidence_seconds, len(json.dumps(evidence, separators=(",", ":"))),
        len(evidence["representative_history"]),
    )
    timings = {"evidence_construction_seconds": evidence_seconds}
    ai_status = "COMPLETE"
    try:
        client = RepositorySynopsisClient()
        synopsis = client.analyze(evidence)
        _validate_synopsis_evidence(synopsis, evidence)
        gemma_client = getattr(client, "_client", None)
        timings.update(getattr(gemma_client, "last_timings", {}))
    except GemmaError as exc:
        ai_status = "FAILED"
        synopsis = build_deterministic_synopsis(overview)
        logger.warning(
            "synopsis AI enrichment unavailable session=%s error_type=%s",
            session_id, type(exc).__name__,
        )
    timings["total_seconds"] = time.perf_counter() - evidence_started
    evidence_preview = _synopsis_preview(overview)
    stored_values = synopsis.model_dump()
    stored_values.update({
        "ai_status": ai_status,
        "evidence_preview": evidence_preview,
        "timings": timings,
    })
    persist_started = time.perf_counter()
    db.store_repository_synopsis(
        session_id,
        GEMMA_MODEL,
        json.dumps(stored_values),
    )
    timings["database_persistence_seconds"] = time.perf_counter() - persist_started
    stored_values["timings"] = timings
    logger.info("synopsis complete session=%s timings=%s", session_id, timings)
    return RepositorySynopsisResponse(
        **synopsis.model_dump(), session_id=session_id, model_name=GEMMA_MODEL,
        created_at=datetime.fromisoformat(db.get_repository_synopsis(session_id)["created_at"]),
        ai_status=ai_status, evidence_preview=evidence_preview, timings=timings,
    )


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
