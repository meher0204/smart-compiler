"""validator.py - Check an AI-proposed edit by running it through our own lexer/parser.

Passing validation means "the front end accepts it and it is a small change". It does NOT
prove the edit matches the programmer's intent: `x = 5 +` -> `x = 5 + 0` parses fine.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

from scompiler.ai.schema import Edit
from scompiler.diagnostics import Diagnostic
from scompiler.lexer import tokenize
from scompiler.parser import parse_source
from scompiler.tokens import TokenType

# An edit that deletes more tokens than this is flagged: deleting code also "fixes" errors.
MAX_REMOVED_TOKENS = 6
# Values the programmer never wrote: new numbers or new names appearing in a fix.
_VALUE_TOKENS = (TokenType.INT_LITERAL, TokenType.FLOAT_LITERAL, TokenType.ID)


class EditError(ValueError):
    """The edit cannot be applied to this source (bad line numbers etc.)."""


class Verdict(str, Enum):
    FIXED_ALL = "fixed_all"  # source now compiles cleanly
    FIXED_TARGET = "fixed_target"  # target error gone, fewer errors overall, others remain
    NO_IMPROVEMENT = "no_improvement"  # target error still there / nothing got better
    WORSE = "worse"  # more errors than before
    INVALID_EDIT = "invalid_edit"  # edit could not be applied
    NO_EDIT = "no_edit"  # model gave an explanation but no concrete edit


@dataclass(frozen=True)
class ValidationResult:
    verdict: Verdict
    errors_before: int = 0
    errors_after: int = 0
    target_resolved: bool = False
    tokens_removed: int = 0
    tokens_added: int = 0
    destructive: bool = False
    invented: List[str] = field(default_factory=list)  # new values/names the fix made up
    corrected_source: Optional[str] = None
    remaining: List[str] = field(default_factory=list)  # messages of errors still present
    reason: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict in (Verdict.FIXED_ALL, Verdict.FIXED_TARGET) and not self.destructive


def apply_edit(source: str, edit: Edit) -> str:
    lines = source.replace("\r\n", "\n").split("\n")
    n = len(lines)
    if not (1 <= edit.start_line <= n + 1):
        raise EditError(f"start_line {edit.start_line} is outside 1..{n + 1}")
    if not (edit.start_line - 1 <= edit.end_line <= n):
        raise EditError(
            f"end_line {edit.end_line} must be between start_line-1 and {n} "
            f"(use end_line = start_line - 1 to insert)"
        )
    new_lines = edit.replacement.split("\n") if edit.replacement != "" else []
    return "\n".join(lines[: edit.start_line - 1] + new_lines + lines[edit.end_line :])


def _lexemes(source: str) -> List[str]:
    tokens, _ = tokenize(source)
    return [t.lexeme for t in tokens if t.type != TokenType.EOF]


def token_delta(before: str, after: str) -> tuple[int, int]:
    """(tokens removed, tokens added) between two sources, using the real lexer."""
    a, b = _lexemes(before), _lexemes(after)
    removed = added = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            removed += i2 - i1
        if op in ("insert", "replace"):
            added += j2 - j1
    return removed, added


def invented_values(before: str, after: str) -> List[str]:
    """Literals/identifiers that the edit added and that appear nowhere in the original source.

    `int x = ;` -> `int x = 0;` invents `0`: the code parses, but the number is a guess.
    `=` -> `==` or `flaot` -> `float` invent no value, so they are not flagged.
    Known gap: illegal characters are dropped by the lexer, so `@` -> `+` is not detected.
    """
    old = [t for t in tokenize(before)[0] if t.type != TokenType.EOF]
    new = [t for t in tokenize(after)[0] if t.type != TokenType.EOF]
    seen = {t.lexeme for t in old}
    matcher = difflib.SequenceMatcher(
        a=[t.lexeme for t in old], b=[t.lexeme for t in new], autojunk=False
    )
    found: List[str] = []
    for op, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if op in ("insert", "replace"):
            for tok in new[j1:j2]:
                if tok.type in _VALUE_TOKENS and tok.lexeme not in seen and tok.lexeme not in found:
                    found.append(tok.lexeme)
    return found


def _errors(source: str) -> List[Diagnostic]:
    return [d for d in parse_source(source).diagnostics if d.is_error]


def validate_edit(
    source: str,
    target: Diagnostic,
    edit: Optional[Edit],
    baseline_errors: Optional[int] = None,
    max_removed_tokens: int = MAX_REMOVED_TOKENS,
    errors_fn: Callable[[str], List[Diagnostic]] = _errors,
) -> ValidationResult:
    before = baseline_errors if baseline_errors is not None else len(errors_fn(source))

    if edit is None:
        return ValidationResult(
            Verdict.NO_EDIT, errors_before=before, errors_after=before,
            reason="the model did not provide a machine-applicable edit",
        )
    try:
        corrected = apply_edit(source, edit)
    except EditError as exc:
        return ValidationResult(
            Verdict.INVALID_EDIT, errors_before=before, errors_after=before, reason=str(exc)
        )

    after_diags = errors_fn(corrected)
    after = len(after_diags)

    # Where did the target error's line end up, and which lines did the edit touch?
    new_count = 0 if edit.replacement == "" else edit.replacement.count("\n") + 1
    delta = new_count - (edit.end_line - edit.start_line + 1)
    new_end = edit.start_line + new_count - 1
    shifted_line = target.line + delta if target.line > edit.end_line else target.line
    lo, hi = edit.start_line - 1, new_end + 1
    still_there = any(
        d.code == target.code and (d.line == shifted_line or lo <= d.line <= hi)
        for d in after_diags
    )

    removed, added = token_delta(source, corrected)
    destructive = removed > max_removed_tokens
    invented = invented_values(source, corrected)
    remaining = [d.message for d in after_diags]

    if after == 0:
        verdict, reason = Verdict.FIXED_ALL, "source now compiles with no errors"
    elif after > before:
        verdict, reason = Verdict.WORSE, f"errors increased from {before} to {after}"
    elif not still_there and after < before:
        verdict, reason = Verdict.FIXED_TARGET, f"errors reduced from {before} to {after}"
    else:
        verdict, reason = Verdict.NO_IMPROVEMENT, "the original error is still reported"

    if destructive:
        reason += f"; WARNING: edit removes {removed} tokens (likely deleting code, not fixing it)"

    if invented:
        reason += "; NOTE: the fix introduces values you never wrote: " + ", ".join(invented)

    return ValidationResult(
        verdict, before, after, not still_there, removed, added, destructive, invented,
        corrected, remaining, reason,
    )
