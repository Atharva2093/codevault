"""Repository ingestion + analysis endpoint.

POST /api/v1/repos          -> ingest + analyze (synchronous, returns 201)
GET  /api/v1/repos/{id}     -> session detail + summary
"""
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from backend.api.schemas import (
    RepoCreate,
    RepositoryDetail,
    CommitSummary,
    DependencyEventSummary,
    DependencyEvidenceSummary,
)
from backend import config
from backend.config import PUBLIC_GIT_HOSTS, MAX_COMMITS_HARD
from backend.db import db
from backend.analysis.git_repo import GitRepository, MANIFEST_FILES
from backend.analysis.manifests import diff_manifests
from backend.analysis.dependency_usage import analyze_dependency_usage


router = APIRouter(prefix="/api/v1/repos", tags=["repositories"])


def _validate_public_git_url(url: str) -> tuple[str, str]:
    """Validate and extract (repo_name, clone_url).

    Accepts:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      git@github.com:owner/repo.git
    Rejects anything else.
    """
    url = url.strip()
    for host in PUBLIC_GIT_HOSTS:
        if host in url:
            if url.startswith(f"git@{host}:"):
                path = url.split(":", 1)[1]
            else:
                path = url.split(host + "/", 1)[1]
            path = path.rstrip(".git")
            if "/" in path:
                return path.replace("/", "-"), url
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"URL must be a public git repo on {', '.join(PUBLIC_GIT_HOSTS)}",
    )


def _session_dir(session_id: str) -> Path:
    return config.DATA_DIR / "clones" / session_id


def _extract_repo_name(clone_url: str) -> str:
    if clone_url.startswith("git@"):
        return clone_url.split(":")[1].rstrip(".git").replace("/", "-")
    parts = clone_url.rstrip("/").rstrip(".git").split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}-{parts[-1]}"
    return "repo"


def _is_manifest_file(path: str) -> bool:
    return os.path.basename(path) in MANIFEST_FILES


def _run_analysis(session_id: str, repo_url: str, max_commits: int) -> RepositoryDetail:
    """Full synchronous pipeline: clone -> commits -> file changes -> deps -> store."""
    clone_path = _session_dir(session_id)
    repo_name = _extract_repo_name(repo_url)

    # 1. Clone
    repo = GitRepository.clone(repo_url, clone_path, max_commits)

    # 2. Commits (oldest-first)
    commits = repo.list_commits(max_commits)
    if not commits:
        db.set_done(session_id, 0)
        return _build_detail(session_id, repo_name, repo_url, max_commits, 0, [], [], [])

    # 3. File changes + classify
    commit_rows: List[tuple] = []
    fc_rows: List[tuple] = []
    dep_event_rows: List[tuple] = []
    commit_summaries: List[CommitSummary] = []
    dep_events_summary: List[DependencyEventSummary] = []

    manifest_files = set()

    for c in commits:
        changes = repo.get_file_changes(c.hash)
        for fc in changes:
            fc_rows.append((session_id, c.hash, fc.path, fc.status, fc.additions, fc.deletions))
            if _is_manifest_file(fc.path):
                manifest_files.add(fc.path)

        commit_rows.append((
            session_id, c.hash, c.author_name, c.author_email,
            c.timestamp.isoformat(), c.message, " ".join(c.parents), c.change_type,
        ))
        commit_summaries.append(CommitSummary(
            hash=c.hash,
            author_name=c.author_name,
            author_email=c.author_email,
            timestamp=c.timestamp,
            message=c.message,
            parents=c.parents,
            change_type=c.change_type,
            file_count=len(changes),
        ))

        # Dependency events: diff against first parent (if any)
        if c.parents:
            parent = c.parents[0]
            for mf in manifest_files:
                parent_content = repo.get_manifest_content(parent, mf)
                head_content = repo.get_manifest_content(c.hash, mf)
                events = diff_manifests(mf, parent_content, head_content)
                for ev in events:
                    dep_event_rows.append((
                        session_id, c.hash, ev.dep_name, ev.kind, ev.manifest_file,
                        ev.action, ev.version, ev.line_number, ev.raw_line, ev.diff_line,
                    ))
                    dep_events_summary.append(DependencyEventSummary(
                        dep_name=ev.dep_name,
                        kind=ev.kind,
                        manifest_file=ev.manifest_file,
                        action=ev.action,
                        version=ev.version,
                        commit_hash=c.hash,
                        old_version=ev.old_version,
                        new_version=ev.new_version,
                    ))

    # 4. Bulk insert
    db.store_commits(session_id, commit_rows)
    db.store_file_changes(session_id, fc_rows)
    if dep_event_rows:
        db.store_dependency_events(session_id, dep_event_rows)

    dependency_evidence = _build_dependency_evidence(clone_path, dep_events_summary)

    # 5. Mark done
    db.set_done(session_id, len(commits))

    return RepositoryDetail(
        id=session_id,
        repo_url=repo_url,
        repo_name=repo_name,
        status="ANALYZED",
        created_at=datetime.now(timezone.utc),
        max_commits=max_commits,
        analyzed_commits=len(commits),
        commits=commit_summaries,
        dependency_events=dep_events_summary,
        dependency_evidence=dependency_evidence,
    )


def _build_detail(session_id: str, repo_name: str, repo_url: str,
                  max_commits: int, analyzed: int,
                  commits: List[CommitSummary],
                  dep_events: List[DependencyEventSummary],
                  dependency_evidence: List[DependencyEvidenceSummary]) -> RepositoryDetail:
    return RepositoryDetail(
        id=session_id,
        repo_url=repo_url,
        repo_name=repo_name,
        status="ANALYZED",
        created_at=datetime.now(timezone.utc),
        max_commits=max_commits,
        analyzed_commits=analyzed,
        commits=commits,
        dependency_events=dep_events,
        dependency_evidence=dependency_evidence,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RepositoryDetail)
def create_repo(payload: RepoCreate):
    repo_name, clone_url = _validate_public_git_url(str(payload.repo_url))
    session_id = uuid.uuid4().hex[:12]

    clone_path = _session_dir(session_id)
    max_commits = min(payload.max_commits, MAX_COMMITS_HARD)

    # Pre-create session (so we can update status on failure)
    db.create_session(session_id, clone_url, repo_name, str(clone_path), max_commits)

    try:
        return _run_analysis(session_id, clone_url, max_commits)
    except Exception as e:
        try:
            db.set_failed(session_id, str(e))
        finally:
            if clone_path.exists():
                shutil.rmtree(clone_path, ignore_errors=True)
            clones_dir = clone_path.parent
            if clones_dir.exists() and not any(clones_dir.iterdir()):
                shutil.rmtree(clones_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {e}",
        )


@router.get("/{session_id}", response_model=RepositoryDetail)
def get_repo(session_id: str):
    row = db.get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    if row["status"] != "ANALYZED":
        return RepositoryDetail(
            id=row["id"],
            repo_url=row["repo_url"],
            repo_name=row["repo_name"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            max_commits=row["max_commits"],
            analyzed_commits=row["analyzed_commits"],
            error=row["error"],
        )

    commit_rows = db.list_commits(session_id)
    dep_rows = db.list_dependency_events(session_id)

    commits = [
        CommitSummary(
            hash=r["commit_hash"],
            author_name=r["author_name"],
            author_email=r["author_email"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            message=r["message"],
            parents=r["parent_hashes"].split(" ") if r["parent_hashes"] else [],
            change_type=r["change_type"],
            file_count=0,
        )
        for r in commit_rows
    ]

    dep_events = [
        DependencyEventSummary(
            dep_name=r["dep_name"],
            kind=r["kind"],
            manifest_file=r["manifest_file"],
            action=r["action"],
            version=r["version"],
            commit_hash=r["commit_hash"],
            old_version=r["old_version"],
            new_version=r["new_version"],
        )
        for r in dep_rows
    ]
    dependency_evidence = _build_dependency_evidence(
        Path(row["clone_path"]), dep_events
    )

    return RepositoryDetail(
        id=row["id"],
        repo_url=row["repo_url"],
        repo_name=row["repo_name"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        max_commits=row["max_commits"],
        analyzed_commits=row["analyzed_commits"],
        commits=commits,
        dependency_events=dep_events,
        dependency_evidence=dependency_evidence,
    )


def _build_dependency_evidence(
    clone_path: Path,
    dependency_events: List[DependencyEventSummary],
) -> List[DependencyEvidenceSummary]:
    return [
        DependencyEvidenceSummary(
            dependency_name=item.dependency_name,
            ecosystem=item.ecosystem,
            manifest_file=item.manifest_file,
            declared_version=item.declared_version,
            current_usage_count=item.current_usage_count,
            current_files=item.current_files,
            historical_dependency_events=[DependencyEventSummary(
                dep_name=event.dep_name,
                kind=event.kind,
                manifest_file=event.manifest_file,
                action=event.action,
                version=event.version,
                commit_hash=event.commit_hash if hasattr(event, "commit_hash") else "",
                old_version=event.old_version,
                new_version=event.new_version,
            ) for event in item.historical_dependency_events],
            current_usage_detected=item.current_usage_detected,
            confidence=item.confidence,
        ) for item in analyze_dependency_usage(clone_path, dependency_events)
    ]