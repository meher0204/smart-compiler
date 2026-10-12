"""explainer.py - Orchestrates prompt -> model -> parse -> validate, with a retry loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from scompiler.ai.client import AIClient, AIUnavailable
from scompiler.ai.prompt import (
    SYSTEM_PROMPT,
    build_feedback,
    build_user_prompt,
    build_validation_feedback,
)
from scompiler.ai.schema import AIResponse, AIResponseError, parse_response
from scompiler.ai.validator import ValidationResult, Verdict, validate_edit
from scompiler.diagnostics import Diagnostic

HIGH, MEDIUM = 0.75, 0.45
INVENTED_CAP = 0.40  # a fix that makes up a value is a guess: never better than "low"


def combine_confidence(model_confidence: float, v: Optional[ValidationResult]) -> float:
    """Final confidence = what the parser verified, scaled by what the model claimed.

    LLM self-reported confidence is poorly calibrated, so the validation outcome dominates:
    a fix that makes the file compile can never score below 0.5; a fix that does not
    validate can never score above 0.2, however sure the model sounded.
    """
    if v is None or v.verdict in (Verdict.INVALID_EDIT, Verdict.WORSE):
        score = 0.1 * model_confidence
    elif v.verdict in (Verdict.NO_EDIT, Verdict.NO_IMPROVEMENT):
        score = 0.2 * model_confidence
    elif v.verdict == Verdict.FIXED_TARGET:
        score = 0.3 + 0.4 * model_confidence
    else:  # FIXED_ALL
        score = 0.5 + 0.5 * model_confidence
    if v is not None and v.destructive:
        score *= 0.5
    if v is not None and v.invented:
        score = min(score, INVENTED_CAP)
    return round(score, 2)


def confidence_label(score: float) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


@dataclass
class Explanation:
    diagnostic: Diagnostic
    response: Optional[AIResponse] = None
    validation: Optional[ValidationResult] = None
    attempts: int = 0
    confidence: float = 0.0
    error: Optional[str] = None  # set when no usable answer was obtained
    attempt_log: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return confidence_label(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        r, v = self.response, self.validation
        return {
            "diagnostic": {"code": self.diagnostic.code, "line": self.diagnostic.line,
                           "column": self.diagnostic.column, "message": self.diagnostic.message},
            "probable_cause": r.probable_cause if r else None,
            "explanation": r.explanation if r else None,
            "suggested_correction": r.suggested_correction if r else None,
            "model_confidence": r.confidence if r else None,
            "confidence": self.confidence,
            "confidence_label": self.label,
            "validation": None if v is None else {
                "verdict": v.verdict.value, "errors_before": v.errors_before,
                "errors_after": v.errors_after, "destructive": v.destructive,
                "tokens_removed": v.tokens_removed, "tokens_added": v.tokens_added,
                "invented": v.invented,
                "reason": v.reason, "corrected_source": v.corrected_source,
            },
            "attempts": self.attempts,
            "error": self.error,
        }


def explain_diagnostic(
    source: str,
    target: Diagnostic,
    all_errors: Sequence[Diagnostic],
    client: AIClient,
    max_attempts: int = 3,
) -> Explanation:
    """Ask the model about `target`; validate each answer; retry with feedback on failure.

    Returns the best attempt (highest combined confidence), not merely the last one.
    """
    others = [d for d in all_errors if d is not target]
    messages: List[Dict[str, str]] = [
        {"role": "user", "content": build_user_prompt(source, target, others)}
    ]
    best: Optional[Explanation] = None
    log: List[str] = []
    last_error: Optional[str] = None
    baseline = len(all_errors)

    for attempt in range(1, max_attempts + 1):
        try:
            raw = client.complete(SYSTEM_PROMPT, messages)
        except AIUnavailable as exc:
            last_error = str(exc)
            log.append(f"attempt {attempt}: {last_error}")
            break  # transport failure: retrying immediately will not help

        messages.append({"role": "assistant", "content": raw})
        try:
            response = parse_response(raw)
        except AIResponseError as exc:
            last_error = f"unusable reply: {exc}"
            log.append(f"attempt {attempt}: {last_error}")
            messages.append({"role": "user", "content": build_feedback(str(exc))})
            continue

        result = validate_edit(source, target, response.edit, baseline_errors=baseline)
        score = combine_confidence(response.confidence, result)
        log.append(f"attempt {attempt}: {result.verdict.value} ({result.reason})")
        candidate = Explanation(target, response, result, attempt, score)
        if best is None or score > best.confidence:
            best = candidate
        if result.accepted:
            break
        messages.append({"role": "user", "content": build_validation_feedback(result)})

    if best is None:
        return Explanation(target, attempts=len(log), error=last_error, attempt_log=log)
    best.attempt_log = log
    best.attempts = len(log)
    return best
