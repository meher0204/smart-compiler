"""schema.py - Structured AI response: parsing and validation of the model's JSON."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


class AIResponseError(ValueError):
    """The model's reply could not be turned into a usable AIResponse."""


@dataclass(frozen=True)
class Edit:
    """Replace source lines start_line..end_line (1-based, inclusive) with `replacement`.

    * insertion:  end_line == start_line - 1   (replaces nothing, inserts before start_line)
    * deletion:   replacement == ""
    """

    start_line: int
    end_line: int
    replacement: str


@dataclass(frozen=True)
class AIResponse:
    probable_cause: str
    explanation: str
    suggested_correction: str  # human-readable description of the fix
    confidence: float  # model's self-reported confidence, clamped to [0, 1]
    edit: Optional[Edit]  # machine-applicable form of the fix (None = no concrete fix)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> Dict[str, Any]:
    """Pull a JSON object out of a model reply, tolerating fences and chatter."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise AIResponseError("reply contained no JSON object") from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIResponseError(f"reply was not valid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise AIResponseError("reply JSON was not an object")
    return data


def _text(data: Dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AIResponseError(f"missing or empty field: {key!r}")
    return value.strip()


def _confidence(data: Dict[str, Any]) -> float:
    raw = data.get("confidence")
    try:
        value = float(raw)  # accepts 0.8 and "0.8"
    except (TypeError, ValueError):
        raise AIResponseError("field 'confidence' must be a number between 0 and 1") from None
    if value > 1.0 and value <= 100.0:  # model answered in percent
        value /= 100.0
    return max(0.0, min(1.0, value))


def _edit(data: Dict[str, Any]) -> Optional[Edit]:
    raw = data.get("edit")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise AIResponseError("field 'edit' must be an object or null")
    try:
        start, end = int(raw["start_line"]), int(raw["end_line"])
        replacement = raw.get("replacement", "")
    except (KeyError, TypeError, ValueError):
        raise AIResponseError("'edit' needs integer start_line and end_line") from None
    if not isinstance(replacement, str):
        raise AIResponseError("'edit.replacement' must be a string")
    return Edit(start, end, replacement)


def parse_response(text: str) -> AIResponse:
    data = extract_json(text)
    return AIResponse(
        probable_cause=_text(data, "probable_cause"),
        explanation=_text(data, "explanation"),
        suggested_correction=_text(data, "suggested_correction"),
        confidence=_confidence(data),
        edit=_edit(data),
    )
