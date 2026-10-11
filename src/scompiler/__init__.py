"""Smart Compiler: fault-tolerant front end with error detection, recovery, and reporting."""

from scompiler.diagnostics import (
    Diagnostic,
    DiagnosticCategory,
    DiagnosticCollector,
    Severity,
)
from scompiler.lexer import Lexer, LexicalError, tokenize
from scompiler.parser import ParseError, Parser, ParseResult, parse_source
from scompiler.recovery import RecoveryManager
from scompiler.report import ErrorReport, generate_report
from scompiler.suggest import suggest
from scompiler.tokens import Token, TokenType

__all__ = [
    "TokenType",
    "Token",
    "Lexer",
    "LexicalError",
    "tokenize",
    "Parser",
    "ParseError",
    "ParseResult",
    "parse_source",
    "Diagnostic",
    "DiagnosticCategory",
    "DiagnosticCollector",
    "Severity",
    "RecoveryManager",
    "suggest",
    "ErrorReport",
    "generate_report",
]
