"""Validated structured responses produced by Gemma."""

from typing import List, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    source_type: Literal["commit", "dependency_event", "file_change", "current_usage"]
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