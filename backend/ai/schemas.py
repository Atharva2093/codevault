"""Validated structured responses produced by Gemma."""

from typing import List, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    source_type: Literal["dependency", "commit", "dependency_event", "file_change", "current_usage"]
    source_id: str
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