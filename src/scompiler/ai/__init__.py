"""AI-assisted diagnostics: explain compiler errors and validate suggested fixes."""

from scompiler.ai.client import (
    AIClient,
    AIUnavailable,
    AnthropicClient,
    GeminiClient,
    ScriptedClient,
    resolve_client,
)
from scompiler.ai.explainer import Explanation, combine_confidence, explain_diagnostic
from scompiler.ai.schema import AIResponse, AIResponseError, Edit, parse_response
from scompiler.ai.validator import ValidationResult, Verdict, apply_edit, validate_edit

__all__ = [
    "AIClient", "AIUnavailable", "AnthropicClient", "GeminiClient", "ScriptedClient",
    "resolve_client",
    "Explanation", "combine_confidence", "explain_diagnostic",
    "AIResponse", "AIResponseError", "Edit", "parse_response",
    "ValidationResult", "Verdict", "apply_edit", "validate_edit",
]
