"""Bounded GitHub issues ingestion and issue intelligence endpoints."""

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, status

from backend.ai.issues import IssueAnalysisClient, build_issue_evidence
from backend.ai.gemma import GemmaError
from backend.ai.schemas import IssueAnalysis
from backend.analysis.repository_overview import build_repository_overview
from backend.api.endpoints.repository import _change_objects, _commit_objects, _session
from backend.api.schemas import IssueAnalysisResponse
from backend.config import GEMMA_MODEL
from backend.db import db
from backend.github import GitHubError, GitHubIssue, fetch_open_issues


router = APIRouter(prefix="/api/v1/repos", tags=["issues"])


def _repo_identity(repo_url: str) -> tuple[str, str]:
    parsed = urlsplit(repo_url)
    if parsed.hostname != "github.com":
        raise HTTPException(status_code=400, detail="GitHub Issues Intelligence requires a GitHub repository")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="Stored repository URL is invalid")
    return parts[-2], parts[-1].removesuffix(".git")


def _load_issues(session_id: str) -> tuple[dict, object, list[GitHubIssue]]:
    row, clone_path = _session(session_id)
    owner, name = _repo_identity(row["repo_url"])
    try:
        issues = fetch_open_issues(owner, name)
    except GitHubError as exc:
        raise HTTPException(status_code=502, detail="GitHub issues are unavailable") from exc
    return row, clone_path, issues


@router.get("/{session_id}/issues", response_model=list[GitHubIssue], status_code=status.HTTP_200_OK)
def list_issues(session_id: str) -> list[GitHubIssue]:
    return _load_issues(session_id)[2]


@router.get(
    "/{session_id}/issues/{issue_number}/analysis",
    response_model=IssueAnalysisResponse,
    status_code=status.HTTP_200_OK,
)
def analyze_issue(session_id: str, issue_number: int) -> IssueAnalysisResponse:
    row, clone_path, issues = _load_issues(session_id)
    issue = next((item for item in issues if item.number == issue_number), None)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found in fetched open issues")
    commits = _commit_objects(session_id)
    changes = _change_objects(session_id)
    overview = build_repository_overview(clone_path, row["repo_url"], commits, changes)
    evidence = build_issue_evidence(
        issue,
        overview["repository"],
        overview["technologies"],
        commits,
        changes,
    )
    try:
        result = IssueAnalysisClient().analyze(evidence.as_dict())
    except GemmaError as exc:
        if "not configured" in str(exc):
            raise HTTPException(status_code=503, detail="Gemma is not configured") from exc
        raise HTTPException(status_code=502, detail="Gemma issue analysis failed") from exc
    _validate_references(result, evidence.allowed_references)
    return IssueAnalysisResponse(**result.model_dump(), model_name=GEMMA_MODEL)


def _validate_references(result: IssueAnalysis, allowed_references: list[str]) -> None:
    allowed = set(allowed_references)
    for reference in result.evidence:
        if f"{reference.source_type}:{reference.source_id}" not in allowed:
            raise HTTPException(status_code=502, detail="Gemma returned an invalid evidence reference")