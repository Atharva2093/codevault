"""Small isolated Google GenAI client for the Gemma product model."""

import os
from typing import Any, Dict

from backend.ai.schemas import DecisionAnalysis
from backend.config import GEMMA_MODEL


class GemmaError(Exception):
    """Raised when Gemma cannot produce a valid structured response."""


SYSTEM_INSTRUCTION = """You are analyzing software repository history.

Use ONLY the supplied evidence. Never invent repository facts, commit hashes, file paths,
dependency names, dates, or PR numbers. Separate FACT, INFERENCE, and UNCERTAINTY in your
reasoning. If the evidence does not support a conclusion, use \"insufficient evidence\".
Return only the requested structured JSON object. Evidence references must use only the
source IDs listed in the supplied evidence package.
"""


class GemmaClient:
    def __init__(self, client: Any = None, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or GEMMA_MODEL
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
        self._client = client

    def analyze(self, evidence: Dict[str, Any]) -> DecisionAnalysis:
        return self.analyze_structured(evidence, SYSTEM_INSTRUCTION, DecisionAnalysis)

    def analyze_structured(self, evidence: Dict[str, Any], instruction: str, schema: Any) -> Any:
        if not self.api_key and self._client is None:
            raise GemmaError("GEMINI_API_KEY is not configured")
        client = self._client or self._build_client()
        prompt = f"{instruction}\n\nEVIDENCE PACKAGE:\n{evidence}"
        try:
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    system_instruction=instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                )
            except ImportError:
                if self._client is None:
                    raise
                config = {
                    "system_instruction": instruction,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                }

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            parsed = getattr(response, "parsed", None)
            if parsed is not None:
                return schema.model_validate(parsed)
            text = getattr(response, "text", None)
            if not text:
                raise GemmaError("Gemma returned an empty response")
            return schema.model_validate_json(text)
        except GemmaError:
            raise
        except Exception as exc:
            raise GemmaError(f"Gemma request failed: {type(exc).__name__}") from exc

    def _build_client(self) -> Any:
        try:
            from google import genai

            return genai.Client(api_key=self.api_key)
        except Exception as exc:
            raise GemmaError(f"Gemma client initialization failed: {type(exc).__name__}") from exc