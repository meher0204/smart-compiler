"""report.py - Final consolidated error report generator.

Transforms collected lexical, syntax, and recovery diagnostics into a clear,
structured summary report designed for terminal display.
"""

from __future__ import annotations

import sys
from typing import List, Optional, TextIO

try:
    from scompiler.diagnostics import Diagnostic, DiagnosticCollector, Severity
except ImportError:
    from diagnostics import Diagnostic, DiagnosticCollector, Severity  # type: ignore

_COLORS = {
    Severity.NOTE: "\033[36m",
    Severity.WARNING: "\033[33m",
    Severity.ERROR: "\033[31;1m",
    Severity.FATAL: "\033[35;1m",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"


class ErrorReport:
    """Generates a structured, human-readable compilation error report."""

    def __init__(
        self,
        collector: DiagnosticCollector,
        source: str = "",
        filename: str = "<input>",
        color: bool = False,
        show_source: bool = False,
    ) -> None:
        self.collector = collector
        self.filename = filename
        self.color = color
        self.show_source = show_source
        self.lines: List[str] = source.splitlines()

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def _source_line(self, number: int) -> Optional[str]:
        if 1 <= number <= len(self.lines):
            return self.lines[number - 1].replace("\t", "    ")
        return None

    def format_category_header(self, d: Diagnostic) -> str:
        cat_name = d.category.capitalize() if d.category else "Syntax"
        sev_name = d.severity.name.capitalize()
        header = f"[{cat_name} {sev_name}] Line {d.line}, Column {d.column}"
        return self._paint(header, _COLORS.get(d.severity, _BOLD))

    def format_diagnostic(self, d: Diagnostic) -> str:
        """Format an individual diagnostic record into the structured report format."""
        out: List[str] = [self.format_category_header(d)]

        out.append(f"Message: {d.message}")

        if d.expected:
            out.append(
                f"Expected: '{d.expected}'" if len(d.expected) == 1 else f"Expected: {d.expected}"
            )

        if d.lexeme:
            out.append(f"Found: '{d.lexeme}'")

        if d.suggestion:
            out.append(self._paint(f"Suggestion: {d.suggestion}", _GREEN))

        if d.recovery_info:
            out.append(self._paint(f"Recovery: {d.recovery_info}", _CYAN))

        for note in d.notes:
            out.append(f"Note: {note}")

        if self.show_source and self.lines:
            sline = self._source_line(d.line)
            if sline is not None:
                width = len(str(d.line))
                out.append(f"  {d.line:>{width}} | {sline}")
                caret = " " * (d.column - 1) + "^" * max(1, d.length)
                out.append(f"  {' ' * width} | {self._paint(caret, _COLORS.get(d.severity, ''))}")

        return "\n".join(out)

    def summary(self) -> str:
        """Produce the final summary text."""
        e_count = self.collector.error_count
        w_count = self.collector.warning_count

        if e_count == 0 and w_count == 0:
            return "Compilation succeeded with no errors."

        text = "Compilation completed with errors. Recovery was attempted."

        if self.collector.limit_reached:
            text += (
                f" (Error limit of {self.collector.max_errors} reached; "
                f"{self.collector.suppressed} further error(s) suppressed.)"
            )
        elif self.collector.suppressed > 0:
            text += f" ({self.collector.suppressed} duplicate or cascading error(s) suppressed.)"

        return text

    def render(self) -> str:
        """Render the complete consolidated error report."""
        sections: List[str] = [
            self._paint("SMART COMPILER — ERROR REPORT", _BOLD),
            f"Total errors: {self.collector.error_count}",
        ]

        if self.collector.has_errors or self.collector.warnings:
            sections.append("")  # Blank line before items
            for d in self.collector.sorted():
                sections.append(self.format_diagnostic(d))
                sections.append("")  # Spacing between errors

        sections.append(self.summary())
        return "\n".join(sections).strip() + "\n"

    def print(self, file: Optional[TextIO] = None) -> None:
        """Print the report to stdout or given file stream."""
        target = file if file is not None else sys.stdout
        target.write(self.render())
        target.flush()

    @property
    def exit_code(self) -> int:
        return 1 if self.collector.has_errors else 0


def generate_report(
    collector: DiagnosticCollector,
    source: str = "",
    filename: str = "<input>",
    color: bool = False,
    show_source: bool = False,
) -> str:
    """Convenience helper to create and render an ErrorReport."""
    return ErrorReport(
        collector, source=source, filename=filename, color=color, show_source=show_source
    ).render()
