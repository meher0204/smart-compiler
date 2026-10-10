from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, IntEnum
from typing import Iterator, List, Optional, Set, Tuple


class Severity(IntEnum):
    NOTE = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3

    @property
    def label(self) -> str:
        return self.name.lower()


class DiagnosticCategory(str, Enum):
    LEXICAL = "lexical"
    SYNTAX = "syntax"
    RECOVERY = "recovery"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class Diagnostic:
    code: str = "SYNTAX_ERROR"
    message: str = ""
    line: int = 1                      # 1-based line number
    column: int = 1                    # 1-based column number
    severity: Severity = Severity.ERROR
    category: str = "syntax"           # "lexical", "syntax", "recovery", etc.
    lexeme: str = ""                   # Found token lexeme (if any)
    expected: Optional[str] = None     # Expected token or description
    length: int = 1                    # How many characters to underline
    suggestion: Optional[str] = None   # Actionable fix suggestion
    recovery_info: Optional[str] = None# Recovery status or action taken
    notes: Tuple[str, ...] = ()        # Additional notes
    related: Optional[Tuple[int, int]] = None  # (line, col) of related token
    token_index: Optional[int] = None  # Index in token stream (if available)

    @property
    def position(self) -> Tuple[int, int]:
        return (self.line, self.column)

    @property
    def is_error(self) -> bool:
        return self.severity >= Severity.ERROR

    def with_suggestion(self, text: Optional[str]) -> "Diagnostic":
        return replace(self, suggestion=text)

    def with_recovery(self, info: Optional[str]) -> "Diagnostic":
        return replace(self, recovery_info=info)

    def with_note(self, note: str) -> "Diagnostic":
        return replace(self, notes=self.notes + (note,))


class DiagnosticCollector:
    """Collects diagnostics across compilation stages without stopping execution.

    Features:
    - Centralized storage for lexical, syntax, and recovery errors.
    - Duplicate suppression at identical source coordinates and error kinds.
    - Configurable error threshold (max_errors) to guard against runaway cascading.
    - Source-order sorting and query helpers.
    """

    def __init__(self, max_errors: int = 50) -> None:
        self.max_errors = max_errors
        self.limit_reached = False
        self.suppressed = 0
        self._items: List[Diagnostic] = []
        self._seen: Set[Tuple] = set()

    # ---- adding diagnostics -----------------------------------------------
    def add(self, diag: Diagnostic) -> bool:
        """Record `diag`. Returns False if it was dropped as duplicate or limit reached."""
        # Key for duplicate suppression: same position, category, and core message/code
        key = (diag.category, diag.code, diag.line, diag.column, diag.message, diag.related)
        if key in self._seen:
            self.suppressed += 1
            return False

        if diag.is_error and self.error_count >= self.max_errors:
            self.limit_reached = True
            self.suppressed += 1
            return False

        self._seen.add(key)
        self._items.append(diag)
        return True

    def error(self, code: str, message: str, line: int, column: int, **kw) -> bool:
        return self.add(Diagnostic(
            code=code,
            message=message,
            line=line,
            column=column,
            severity=Severity.ERROR,
            category=kw.pop("category", "syntax"),
            **kw,
        ))

    def warning(self, code: str, message: str, line: int, column: int, **kw) -> bool:
        return self.add(Diagnostic(
            code=code,
            message=message,
            line=line,
            column=column,
            severity=Severity.WARNING,
            category=kw.pop("category", "syntax"),
            **kw,
        ))

    def add_lexical_error(
        self,
        message: str,
        line: int,
        column: int,
        lexeme: str = "",
        code: str = "LEX_ERROR",
        **kw,
    ) -> bool:
        return self.add(Diagnostic(
            code=code,
            message=message,
            line=line,
            column=column,
            severity=Severity.ERROR,
            category=DiagnosticCategory.LEXICAL.value,
            lexeme=lexeme,
            **kw,
        ))

    def add_syntax_error(
        self,
        message: str,
        line: int,
        column: int,
        lexeme: str = "",
        expected: Optional[str] = None,
        suggestion: Optional[str] = None,
        recovery_info: Optional[str] = None,
        code: str = "SYNTAX_ERROR",
        **kw,
    ) -> bool:
        return self.add(Diagnostic(
            code=code,
            message=message,
            line=line,
            column=column,
            severity=Severity.ERROR,
            category=DiagnosticCategory.SYNTAX.value,
            lexeme=lexeme,
            expected=expected,
            suggestion=suggestion,
            recovery_info=recovery_info,
            **kw,
        ))

    # ---- querying ---------------------------------------------------------
    @property
    def diagnostics(self) -> List[Diagnostic]:
        return list(self._items)

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self._items if d.is_error]

    @property
    def warnings(self) -> List[Diagnostic]:
        return [d for d in self._items if d.severity == Severity.WARNING]

    @property
    def error_count(self) -> int:
        return sum(1 for d in self._items if d.is_error)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def sorted(self) -> List[Diagnostic]:
        """Return diagnostics in source order (line, column)."""
        return sorted(self._items, key=lambda d: (d.line, d.column))

    def update_diagnostic_suggestion(self, index: int, suggestion: str) -> None:
        if 0 <= index < len(self._items):
            self._items[index] = self._items[index].with_suggestion(suggestion)

    def apply_suggestions(self, suggester_fn) -> None:
        """Apply a suggestion function across all stored diagnostics."""
        for i, diag in enumerate(self._items):
            if not diag.suggestion:
                sug = suggester_fn(diag)
                if sug:
                    self._items[i] = diag.with_suggestion(sug)

    def clear(self) -> None:
        self._items.clear()
        self._seen.clear()
        self.suppressed = 0
        self.limit_reached = False

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)