"""Gemma-backed structured repository synopsis."""

import json
from typing import Any

from backend.ai.gemma import GemmaError
from backend.ai.schemas import RepositorySynopsis
from backend.config import GEMMA_MODEL


SYNOPSIS_INSTRUCTION = """You explain a software repository using ONLY the supplied deterministic evidence.
Separate direct facts from reasonable inference and uncertainty. Never invent technologies,
users, adoption, architecture, dates, authors, commit hashes, or file paths. If evidence is
insufficient, say \"Insufficient evidence.\" Return only the requested JSON object."""


class RepositorySynopsisClient:
    def __init__(self, client: Any = None, model: str | None = None, api_key: str | None = None) -> None:
        from backend.ai.gemma import GemmaClient

        self._client = GemmaClient(client=client, model=model, api_key=api_key)

    def analyze(self, evidence: dict) -> RepositorySynopsis:
        prompt = f"{SYNOPSIS_INSTRUCTION}\n\nREPOSITORY EVIDENCE:\n{json.dumps(evidence, separators=(',', ':'))}"
        if not self._client.api_key and self._client._client is None:
            raise GemmaError("GEMINI_API_KEY is not configured")
        client = self._client._client or self._client._build_client()
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=SYNOPSIS_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=RepositorySynopsis,
            )
            response = client.models.generate_content(model=self._client.model, contents=prompt, config=config)
            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                return RepositorySynopsis.model_validate(parsed)
            text = getattr(response, "text", None)
            if not text:
                raise GemmaError("Gemma returned an empty response")
            return RepositorySynopsis.model_validate_json(text)
        except GemmaError:
            raise
        except Exception as exc:
            raise GemmaError(f"Gemma synopsis failed: {type(exc).__name__}") from exc


__all__ = ["RepositorySynopsisClient"]
