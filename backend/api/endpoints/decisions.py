"""Gemma-backed decision extraction endpoint."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, status

from backend.ai.evidence import build_evidence_package
from backend.ai.gemma import GemmaClient, GemmaError
from backend.ai.schemas import DecisionAnalysis
from backend.api.schemas import DecisionAnalysisRequest, DependencyEventSummary, StoredDecisionAnalysis
from backend.config import GEMMA_MODEL
from backend.db import db


router = APIRouter(prefix="/api/v1/repos", tags=["decisions"])


@router.post(
    "/{session_id}/decisions/analyze",
    response_model=DecisionAnalysis,
    status_code=status.HTTP_200_OK,
)
def analyze_decision(session_id: str, payload: DecisionAnalysisRequest) -> DecisionAnalysis:
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "ANALYZED":
        raise HTTPException(status_code=409, detail="Repository analysis is not complete")

    clone_path = Path(session["clone_path"])
    if not clone_path.exists():
        raise HTTPException(status_code=409, detail="Repository clone is unavailable")

    commits = [_commit_object(row) for row in db.list_commits(session_id)]
    changes = [_change_object(row) for row in db.list_file_changes(session_id)]
    events = [_event_model(row) for row in db.list_dependency_events(session_id)]
    package = build_evidence_package(
        clone_path,
        payload.dependency_name,
        events,
        commits,
        changes,
        commit_lookup={commit.hash: commit for commit in commits},
        selected_commit_hash=payload.commit_hash,
    )
    if package.dependency is None and not package.dependency_events:
        raise HTTPException(status_code=404, detail="Dependency or historical event not found")

    try:
        analysis = GemmaClient().analyze(package.as_dict())
    except GemmaError as exc:
        message = str(exc)
        if "not configured" in message:
            raise HTTPException(status_code=503, detail="Gemma is not configured") from exc
        raise HTTPException(status_code=502, detail="Gemma analysis failed") from exc

    _validate_references(analysis, package)
    db.store_decision_analysis(
        session_id=session_id,
        target=payload.dependency_name,
        model_name=GEMMA_MODEL,
        decision=analysis.decision,
        reason=analysis.reason,
        evidence_json=json.dumps([reference.model_dump() for reference in analysis.evidence]),
        affected_files_json=json.dumps(analysis.affected_files),
        current_validity=analysis.current_validity,
        confidence=analysis.confidence,
        uncertainty=analysis.uncertainty,
    )
    return analysis


@router.get(
    "/{session_id}/decisions",
    response_model=list[StoredDecisionAnalysis],
    status_code=status.HTTP_200_OK,
)
def list_decisions(session_id: str) -> list[StoredDecisionAnalysis]:
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        StoredDecisionAnalysis(
            id=row["id"],
            session_id=row["session_id"],
            target=row["target"],
            model_name=row["model_name"],
            decision=row["decision"],
            reason=row["reason"],
            evidence=json.loads(row["evidence_json"]),
            affected_files=json.loads(row["affected_files_json"]),
            current_validity=row["current_validity"],
            confidence=row["confidence"],
            uncertainty=row["uncertainty"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in db.list_decision_analyses(session_id)
    ]


def _validate_references(analysis: DecisionAnalysis, package) -> None:
    allowed = set(package.allowed_references)
    for reference in analysis.evidence:
        full_reference = f"{reference.source_type}:{reference.source_id}"
        if full_reference not in allowed:
            raise HTTPException(status_code=502, detail="Gemma returned an invalid evidence reference")

    allowed_files = set(package.dependency.get("current_files", []) if package.dependency else [])
    allowed_files.update(change["path"] for change in package.file_changes)
    if package.dependency:
        allowed_files.add(package.dependency["manifest_file"])
    unknown_files = set(analysis.affected_files) - allowed_files
    if unknown_files:
        raise HTTPException(status_code=502, detail="Gemma returned an invalid affected file")


def _event_model(row) -> DependencyEventSummary:
    keys = row.keys()
    return DependencyEventSummary(
        dep_name=row["dep_name"],
        kind=row["kind"],
        manifest_file=row["manifest_file"],
        action=row["action"],
        version=row["version"],
        commit_hash=row["commit_hash"],
        old_version=row["old_version"] if "old_version" in keys else None,
        new_version=row["new_version"] if "new_version" in keys else None,
    )


def _commit_object(row):
    return SimpleNamespace(
        hash=row["commit_hash"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        message=row["message"],
        change_type=row["change_type"],
        parents=row["parent_hashes"].split() if row["parent_hashes"] else [],
    )


def _change_object(row):
    return SimpleNamespace(
        commit_hash=row["commit_hash"],
        path=row["path"],
        status=row["status"],
        additions=row["additions"],
        deletions=row["deletions"],
    )