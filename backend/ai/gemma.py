"""Small isolated Google GenAI client for the Gemma product model."""

import os
import time
import logging
import json
import re
from typing import Any, Dict

from pydantic import ValidationError

from backend.ai.schemas import DecisionAnalysis
from backend.config import GEMMA_MAX_RETRIES, GEMMA_MODEL, GEMMA_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


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
        self.last_timings: dict[str, float] = {}

    def analyze(self, evidence: Dict[str, Any]) -> DecisionAnalysis:
        return self.analyze_structured(evidence, SYSTEM_INSTRUCTION, DecisionAnalysis)

    def analyze_structured(
        self,
        evidence: Dict[str, Any],
        instruction: str,
        schema: Any,
        wire_schema: Any = None,
    ) -> Any:
        if not self.api_key and self._client is None:
            raise GemmaError("GEMINI_API_KEY is not configured")
        if self._client is None:
            self._client = self._build_client()
        client = self._client
        prompt = json.dumps(evidence, separators=(",", ":"), sort_keys=True)
        try:
            try:
                from google.genai import types
                config = types.GenerateContentConfig(
                    system_instruction=instruction,
                    response_mime_type="application/json",
                    response_schema=wire_schema or schema,
                )
            except ValidationError as exc:
                _log_validation_failure("sdk_config", exc, self.model)
                raise GemmaError(
                    f"Gemma SDK configuration validation failed: {_validation_summary(exc)}"
                ) from exc
            except ImportError:
                if self._client is None:
                    raise
                config = {
                    "system_instruction": instruction,
                    "response_mime_type": "application/json",
                    "response_schema": wire_schema or schema,
                }

            request_started = time.perf_counter()
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            response_received = time.perf_counter()
            try:
                parsed = getattr(response, "parsed", None)
            except ValidationError as exc:
                _log_validation_failure("sdk_response", exc, self.model)
                raise GemmaError(
                    f"Gemma SDK response validation failed: {_validation_summary(exc)}"
                ) from exc
            if parsed is not None:
                try:
                    result = schema.model_validate(parsed)
                except ValidationError as exc:
                    _log_validation_failure("response_model", exc, self.model)
                    raise GemmaError(
                        f"Gemma response validation failed: {_validation_summary(exc)}"
                    ) from exc
                parsed_at = time.perf_counter()
                self.last_timings = {
                    "gemma_request_seconds": response_received - request_started,
                    "response_parsing_seconds": parsed_at - response_received,
                }
                return result
            text = getattr(response, "text", None)
            if not text:
                raise GemmaError("Gemma returned an empty response")
            try:
                result = schema.model_validate_json(_normalize_json_response(text))
            except ValidationError as exc:
                _log_validation_failure("response_json", exc, self.model)
                raise GemmaError(
                    f"Gemma response JSON validation failed: {_validation_summary(exc)}"
                ) from exc
            parsed_at = time.perf_counter()
            self.last_timings = {
                "gemma_request_seconds": response_received - request_started,
                "response_parsing_seconds": parsed_at - response_received,
            }
            return result
        except GemmaError:
            raise
        except Exception as exc:
            _log_provider_exception(exc, self.model)
            if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower() or "deadline" in type(exc).__name__.lower():
                raise GemmaError("Gemma analysis timed out") from exc
            status = _provider_status(exc)
            if status in {429, 500, 503, 504}:
                if status == 504:
                    raise GemmaError("Gemma analysis timed out: provider deadline exceeded") from exc
                raise GemmaError(f"Gemma provider returned HTTP {status}") from exc
            if "connect" in type(exc).__name__.lower() or "network" in type(exc).__name__.lower():
                raise GemmaError("Gemma network request failed") from exc
            raise GemmaError(f"Gemma request failed: {type(exc).__name__}") from exc

    def _build_client(self) -> Any:
        try:
            from google import genai
            from google.genai import types

            return genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=int(GEMMA_TIMEOUT_SECONDS * 1000),
                    retry_options=types.HttpRetryOptions(
                        attempts=GEMMA_MAX_RETRIES + 1,
                        initial_delay=0.5,
                        max_delay=1.5,
                        jitter=0.1,
                        http_status_codes=[429, 500, 503, 504],
                    ),
                ),
            )
        except Exception as exc:
            raise GemmaError(f"Gemma client initialization failed: {type(exc).__name__}") from exc


def _normalize_json_response(text: str) -> str:
    """Remove only a complete optional Markdown JSON fence."""
    value = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.IGNORECASE | re.DOTALL)
    return fenced.group(1).strip() if fenced else value


def _log_provider_exception(exc: Exception, model: str) -> None:
    """Log provider diagnostics without request contents, headers, or credentials."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    details = getattr(exc, "details", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is None and response is not None:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("retry-after")
    logger.error(
        "Gemma provider failure class=%s model=%s status=%s code=%s details_present=%s retry_after=%s",
        type(exc).__name__, model, status, getattr(exc, "code", None),
        details is not None, retry_after,
    )


def _provider_status(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _validation_summary(exc: ValidationError) -> str:
    errors = exc.errors(include_context=False, include_url=False)
    fields = []
    for error in errors[:5]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "root"
        fields.append(f"{location}:{error.get('type', 'invalid')}")
    suffix = ",..." if len(errors) > 5 else ""
    return "fields=" + ",".join(fields) + suffix


def _log_validation_failure(stage: str, exc: ValidationError, model: str) -> None:
    logger.error(
        "Gemma validation failure stage=%s class=%s model=%s summary=%s",
        stage, type(exc).__name__, model, _validation_summary(exc),
    )
