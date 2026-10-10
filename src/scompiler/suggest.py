"""suggest.py - Rule-based fix suggestions for compiler diagnostics.

Provides deterministic, rule-based suggestions for common lexical and syntax errors,
including missing semicolons, parentheses, braces, operator misuse, and keyword typos.
"""
from __future__ import annotations

import difflib
from typing import Callable, Dict, Iterable, Optional

try:
    from scompiler.diagnostics import Diagnostic
except ImportError:
    from diagnostics import Diagnostic  # type: ignore


KEYWORDS = (
    "int", "float", "if", "else", "while", "return", "printf",
)

_OPERATORS = set("+-*/%<>!&|^") | {"==", "!=", "<=", ">=", "="}


# ---- helpers ----------------------------------------------------------------
def closest_keyword(
    word: str,
    keywords: Iterable[str] = KEYWORDS,
    cutoff: float = 0.65,
) -> Optional[str]:
    """Return the keyword `word` is probably a typo of, else None."""
    if not word or word in keywords:
        return None
    matches = difflib.get_close_matches(word.lower(), list(keywords), n=1, cutoff=cutoff)
    return matches[0] if matches else None


# ---- suggestion rules -------------------------------------------------------
def _suggest_missing_semicolon(d: Diagnostic) -> Optional[str]:
    if d.lexeme and d.lexeme not in ("EOF", ";", "{", "}"):
        return f"Insert ';' after '{d.lexeme}'."
    return "Insert ';' after the previous statement."


def _suggest_missing_rparen(d: Diagnostic) -> Optional[str]:
    if d.related:
        return f"Insert ')' to close the '(' opened on line {d.related[0]}."
    if "condition" in d.message.lower() or "if" in d.message.lower() or "while" in d.message.lower():
        return "Insert ')' to close the condition."
    return "Insert ')' to close the parenthesized expression or argument list."


def _suggest_missing_rbrace(d: Diagnostic) -> Optional[str]:
    if d.related:
        return f"Insert '}}' to close the block opened on line {d.related[0]}."
    if d.lexeme == "EOF" or "end of file" in d.message.lower() or "eof" in d.message.lower():
        return "Insert '}' before the end of the file."
    return "Insert '}' to close the current block."


def _suggest_unexpected_token(d: Diagnostic) -> Optional[str]:
    lex = d.lexeme
    msg = d.message.lower()

    if not lex:
        if d.expected:
            return f"Insert expected '{d.expected}'."
        return None

    if lex == "else" and "expected" in msg:
        return "'else' must directly follow an 'if' statement or block."

    if lex == ",":
        return "Remove the stray ','."

    if lex == ";":
        if "expression" in msg:
            return "Provide a valid value or expression before ';'."
        return "Remove the redundant ';'."

    if lex == "=" and ("condition" in msg or "comparison" in msg or "expected ')'" in msg):
        return "Use '==' for comparison; '=' is an assignment operator."

    if lex in ("+", "-", "*", "/", "%"):
        return f"Provide an operand before or after operator '{lex}'."

    if lex.isidentifier():
        kw = closest_keyword(lex)
        if kw:
            return f"Did you mean keyword '{kw}'?"

    if d.expected:
        return f"Expected '{d.expected}', but found '{lex}'."

    return None


def _suggest_lexical_error(d: Diagnostic) -> Optional[str]:
    msg = d.message.lower()
    lex = d.lexeme

    if "malformed number" in msg:
        return "Ensure numeric literals contain only valid digits and standard decimal format (e.g., 123 or 3.14)."
    if "unterminated string" in msg:
        return 'Add a closing quote `"` to complete the string literal.'
    if "unterminated block comment" in msg:
        return "Add `*/` to close the block comment."
    if "illegal character" in msg:
        return f"Remove invalid character {lex!r} not supported by the language grammar."
    if "string literals are not supported" in msg:
        return "The language grammar currently only supports integer and float expressions."

    return None


def _suggest_unclosed_block(d: Diagnostic) -> Optional[str]:
    if d.related:
        return f"Insert '}}' to balance block opened on line {d.related[0]}."
    return "Insert '}' before the end of the file."


RULES: Dict[str, Callable[[Diagnostic], Optional[str]]] = {
    "E001": _suggest_missing_semicolon,
    "MISSING_SEMICOLON": _suggest_missing_semicolon,
    "E002": _suggest_missing_rparen,
    "MISSING_RPAREN": _suggest_missing_rparen,
    "E003": _suggest_missing_rbrace,
    "MISSING_RBRACE": _suggest_missing_rbrace,
    "UNCLOSED_BLOCK": _suggest_unclosed_block,
    "E004": _suggest_unexpected_token,
    "SYNTAX_ERROR": _suggest_unexpected_token,
    "LEX_ERROR": _suggest_lexical_error,
}


def suggest(diag: Diagnostic) -> Optional[str]:
    """Return a simple, deterministic rule-based suggestion for `diag`, or None."""
    # First check if diagnostic already has an explicitly provided suggestion
    if diag.suggestion:
        return diag.suggestion

    # Check by specific error code rule
    if diag.code in RULES:
        res = RULES[diag.code](diag)
        if res:
            return res

    # Infer from message or expected/found fields
    msg = diag.message.lower()
    exp = (diag.expected or "").lower()

    if "semicolon" in msg or exp == ";":
        return _suggest_missing_semicolon(diag)
    if "rparen" in msg or "parenthesis" in msg or exp == ")":
        return _suggest_missing_rparen(diag)
    if "rbrace" in msg or "brace" in msg or "unclosed block" in msg or exp == "}":
        return _suggest_missing_rbrace(diag)
    if diag.category == "lexical":
        return _suggest_lexical_error(diag)

    return _suggest_unexpected_token(diag)