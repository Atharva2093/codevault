"""Gemma-backed structured repository synopsis."""

from typing import Any

from backend.ai.gemma import GemmaError
from backend.ai.schemas import RepositorySynopsis
from backend.config import GEMMA_MODEL


SYNOPSIS_INSTRUCTION = """You explain a software repository using ONLY the supplied deterministic evidence.
Do not invent facts. Use exact supplied evidence references. Return only this JSON object,
with purpose, what_it_does, project_evolution_summary, current_state_summary, confidence,
uncertainty, and optional primary_technologies, major_components, and evidence. Evidence
source_type is the prefix before the first colon and source_id is the remainder. Use an empty
evidence array when no supplied reference supports a claim. No Markdown or explanation."""


REPOSITORY_SYNOPSIS_WIRE_SCHEMA = {
    "type": "object",
    "properties": {
        "purpose": {"type": "string"},
        "what_it_does": {"type": "string"},
        "primary_technologies": {"type": "array", "items": {"type": "string"}},
        "major_components": {"type": "array", "items": {"type": "string"}},
        "project_evolution_summary": {"type": "string"},
        "current_state_summary": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "uncertainty": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_type": {"type": "string", "enum": ["commit"]},
                    "source_id": {"type": "string"},
                    "claim": {"type": "string"},
                },
                "required": ["source_type", "source_id", "claim"],
            },
        },
    },
    "required": [
        "purpose", "what_it_does", "project_evolution_summary",
        "current_state_summary", "confidence", "uncertainty",
    ],
}


class RepositorySynopsisClient:
    def __init__(self, client: Any = None, model: str | None = None, api_key: str | None = None) -> None:
        from backend.ai.gemma import GemmaClient

        self._client = GemmaClient(client=client, model=model, api_key=api_key)

    def analyze(self, evidence: dict) -> RepositorySynopsis:
        try:
            return self._client.analyze_structured(
                evidence,
                SYNOPSIS_INSTRUCTION,
                RepositorySynopsis,
                wire_schema=REPOSITORY_SYNOPSIS_WIRE_SCHEMA,
            )
        except GemmaError:
            raise


def build_deterministic_synopsis(overview: dict) -> RepositorySynopsis:
    repository = overview.get("repository", {})
    name = repository.get("name") or "this repository"
    technologies = [item.get("name") for item in overview.get("technologies", []) if item.get("name")]
    structure = [item for item in overview.get("structure", []) if item]
    history = overview.get("history", [])
    technology_text = ", ".join(technologies[:5]) or "no recognized technologies"
    structure_text = ", ".join(structure[:5]) or "no top-level structure was detected"
    if history:
        evolution = f"Deterministic analysis includes {len(history)} representative commits; recent work includes {history[-1].get('message', 'an observed change')}."
    else:
        evolution = "No commit history was available in the analyzed evidence."
    return RepositorySynopsis(
        purpose=f"{name} is a public software repository analyzed from its local evidence.",
        what_it_does=f"Its evidence indicates technologies including {technology_text}, with top-level areas such as {structure_text}.",
        primary_technologies=technologies[:8],
        major_components=structure[:8],
        project_evolution_summary=evolution,
        current_state_summary="The current state is described by deterministic repository evidence; AI enrichment was unavailable.",
        confidence="low",
        uncertainty="Gemma enrichment was unavailable; this synopsis contains deterministic facts only.",
        evidence=[],
    )


__all__ = ["RepositorySynopsisClient"]
