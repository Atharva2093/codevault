"""Deterministic MVP insight endpoints built from stored repository evidence."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.analysis.dependency_usage import analyze_dependency_usage
from backend.api.schemas import DependencyEventSummary
from backend.db import db


router = APIRouter(prefix="/api/v1/repos", tags=["insights"])


def _session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "ANALYZED":
        raise HTTPException(status_code=409, detail="Repository analysis is not complete")
    return session


def _events(session_id: str) -> list[DependencyEventSummary]:
    rows = db.list_dependency_events(session_id)
    return [
        DependencyEventSummary(
            dep_name=row["dep_name"],
            kind=row["kind"],
            manifest_file=row["manifest_file"],
            action=row["action"],
            version=row["version"],
            commit_hash=row["commit_hash"],
            old_version=row["old_version"] if "old_version" in row.keys() else None,
            new_version=row["new_version"] if "new_version" in row.keys() else None,
        )
        for row in rows
    ]


@router.get("/{session_id}/timeline")
def decision_timeline(session_id: str) -> list[dict]:
    _session(session_id)
    commits = db.list_commits(session_id)
    events_by_commit: dict[str, list[dict]] = {}
    for event in _events(session_id):
        events_by_commit.setdefault(event.commit_hash, []).append(event.model_dump())
    return [
        {
            "commit_hash": row["commit_hash"],
            "timestamp": row["timestamp"],
            "author": row["author_name"],
            "message": row["message"],
            "change_type": row["change_type"],
            "dependency_events": events_by_commit.get(row["commit_hash"], []),
        }
        for row in commits
    ]


@router.get("/{session_id}/dependencies/ghosts")
def ghost_dependencies(session_id: str) -> list[dict]:
    session = _session(session_id)
    evidence = analyze_dependency_usage(Path(session["clone_path"]), _events(session_id))
    return [
        {
            "dependency_name": item.dependency_name,
            "ecosystem": item.ecosystem,
            "manifest_file": item.manifest_file,
            "declared_version": item.declared_version,
            "usage_status": "definitely_unused" if not item.current_usage_detected else "used",
            "current_usage_count": item.current_usage_count,
            "current_files": item.current_files,
            "confidence": item.confidence,
        }
        for item in evidence
        if not item.current_usage_detected
    ]


@router.get("/{session_id}/dependencies/{dependency_name}/decay")
def dependency_decay(session_id: str, dependency_name: str) -> dict:
    session = _session(session_id)
    events = [event for event in _events(session_id) if event.dep_name.lower() == dependency_name.lower()]
    evidence = analyze_dependency_usage(Path(session["clone_path"]), events)
    current = next((item for item in evidence if item.dependency_name.lower() == dependency_name.lower()), None)
    if not events and current is None:
        raise HTTPException(status_code=404, detail="Dependency history not found")
    return {
        "dependency_name": dependency_name,
        "original_decision": events[0].action if events else "current declaration",
        "original_evidence": [event.model_dump() for event in events],
        "current_evidence": {
            "current_usage_detected": current.current_usage_detected if current else False,
            "current_usage_count": current.current_usage_count if current else 0,
            "current_files": current.current_files if current else [],
        },
        "validity": "supported" if current and current.current_usage_detected else "not currently supported",
        "confidence": current.confidence if current else "low",
        "uncertainty": "Historical intent is inferred from commit and manifest evidence only.",
    }


@router.get("/{session_id}/dependencies/{dependency_name}/counterfactual")
def dependency_counterfactual(session_id: str, dependency_name: str) -> dict:
    session = _session(session_id)
    events = [event for event in _events(session_id) if event.dep_name.lower() == dependency_name.lower()]
    evidence = analyze_dependency_usage(Path(session["clone_path"]), events)
    current = next((item for item in evidence if item.dependency_name.lower() == dependency_name.lower()), None)
    if current is None and not events:
        raise HTTPException(status_code=404, detail="Dependency history not found")
    return {
        "dependency_name": dependency_name,
        "current_files": current.current_files if current else [],
        "current_usage_count": current.current_usage_count if current else 0,
        "historical_events": [event.model_dump() for event in events],
        "likely_impact": "removal_requires_review" if current and current.current_usage_detected else "no_current_import_detected",
        "confidence": current.confidence if current else "low",
        "uncertainty": "Static import analysis cannot prove runtime or configuration-only usage.",
    }