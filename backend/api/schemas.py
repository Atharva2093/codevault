"""Pydantic models for API requests, responses, and evidence traceability."""

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl

from backend.ai.schemas import ContributionGuidance, DecisionAnalysis, IssueAnalysis, RepositorySynopsis


# ---- Request / Input ----

class RepoCreate(BaseModel):
    repo_url: HttpUrl
    max_commits: int = Field(default=100, ge=1)


# ---- Evidence traceability ----

class EvidenceItem(BaseModel):
    """Every AI conclusion must trace to one or more EvidenceItems."""
    source_type: Literal["commit", "file_change", "dependency_event", "session"]
    source_id: str
    title: str
    context: str


# ---- Response models ----

class RepositoryBase(BaseModel):
    id: str
    repo_url: str
    repo_name: Optional[str] = None
    status: Literal["PENDING", "ANALYZING", "ANALYZED", "FAILED"]
    created_at: datetime
    max_commits: int
    analyzed_commits: int = 0
    error: Optional[str] = None


class RepositoryDetail(RepositoryBase):
    commits: List["CommitSummary"] = []
    dependency_events: List["DependencyEventSummary"] = []
    dependency_evidence: List["DependencyEvidenceSummary"] = []


class CommitSummary(BaseModel):
    hash: str
    author_name: str
    author_email: str
    timestamp: datetime
    message: str
    parents: List[str] = []
    change_type: str
    file_count: int = 0


class FileChangeSummary(BaseModel):
    path: str
    status: str
    additions: int
    deletions: int


class DependencyEventSummary(BaseModel):
    dep_name: str
    kind: str
    manifest_file: str
    action: str  # added | removed | changed
    version: Optional[str] = None
    commit_hash: str
    old_version: Optional[str] = None
    new_version: Optional[str] = None


class DependencyEvidenceSummary(BaseModel):
    dependency_name: str
    ecosystem: Literal["python", "javascript"]
    manifest_file: str
    declared_version: Optional[str] = None
    current_usage_count: int = 0
    current_files: List[str] = []
    historical_dependency_events: List[DependencyEventSummary] = []
    current_usage_detected: bool = False
    confidence: Literal["high", "medium", "low"]


class DecisionAnalysisRequest(BaseModel):
    dependency_name: str = Field(min_length=1)
    commit_hash: Optional[str] = None


class StoredDecisionAnalysis(DecisionAnalysis):
    id: int
    session_id: str
    target: str
    model_name: str
    created_at: datetime


class RepositorySynopsisResponse(RepositorySynopsis):
    session_id: str
    model_name: str
    created_at: datetime
    evidence_status: Literal["COMPLETE"] = "COMPLETE"
    ai_status: Literal["RUNNING", "COMPLETE", "FAILED"] = "COMPLETE"
    evidence_preview: dict = Field(default_factory=dict)
    timings: dict[str, float] = Field(default_factory=dict)


class IssueAnalysisResponse(IssueAnalysis):
    model_name: str


class ContributionGuidanceResponse(ContributionGuidance):
    model_name: str



# Forward refs
RepositoryDetail.model_rebuild()
CommitSummary.model_rebuild()
DependencyEventSummary.model_rebuild()
DependencyEvidenceSummary.model_rebuild()