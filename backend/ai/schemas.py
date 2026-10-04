"""Validated structured responses produced by Gemma."""

from typing import List, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    source_type: Literal["dependency", "commit", "dependency_event", "file_change", "current_usage", "issue", "technology"]
    source_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)


class DecisionAnalysis(BaseModel):
    decision: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: List[EvidenceReference] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)
    current_validity: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    uncertainty: str = Field(min_length=1)


class RepositorySynopsis(BaseModel):
    purpose: str = Field(min_length=1)
    what_it_does: str = Field(min_length=1)
    primary_technologies: list[str] = Field(default_factory=list)
    major_components: list[str] = Field(default_factory=list)
    project_evolution_summary: str = Field(min_length=1)
    current_state_summary: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    uncertainty: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ProjectArchaeology(BaseModel):
    what_changed: str = Field(min_length=1)
    facts: list[str] = Field(default_factory=list)
    likely_reason: str = Field(min_length=1)
    reasoning: list[str] = Field(default_factory=list)
    uncertainty: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low"]
    evidence: list[EvidenceReference] = Field(default_factory=list)


class IssueAnalysis(BaseModel):
    issue_number: int = Field(ge=1)
    summary: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    likely_affected_area: str = Field(min_length=1)
    relevant_technologies: list[str] = Field(default_factory=list)
    estimated_complexity: Literal["low", "medium", "high", "unknown"]
    required_skills: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    uncertainty: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)


class ContributionGuidance(BaseModel):
    issue_number: int = Field(ge=1)
    recommendation: Literal["good_starting_point", "needs_project_context", "complex_change", "insufficient_evidence"]
    why_this_issue: str = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    relevant_skills: list[str] = Field(default_factory=list)
    relevant_technologies: list[str] = Field(default_factory=list)
    affected_area: str = Field(min_length=1)
    estimated_complexity: Literal["low", "medium", "high", "unknown"]
    suggested_first_steps: list[str] = Field(default_factory=list)
    relevant_history: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]
    uncertainty: str = Field(min_length=1)
    evidence: list[EvidenceReference] = Field(default_factory=list)