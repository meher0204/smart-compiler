"""cli.py - Command-line interface: compile a file, optionally explain errors with AI.

    scompiler prog.src                  # report only (offline, deterministic)
    scompiler prog.src --explain        # + AI cause / explanation / validated fix
    scompiler prog.src --explain --json # machine-readable
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from typing import Callable, List, Optional, TextIO

from rich.console import Console

from scompiler.ai.client import PROVIDERS, AIClient, AIUnavailable, GeminiClient, resolve_client
from scompiler.ai.explainer import Explanation, explain_diagnostic
from scompiler.ai.validator import Verdict
from scompiler.parser import parse_source

ClientFactory = Callable[[str, Optional[str]], AIClient]  # (provider, model) -> client

_VERDICT_TEXT = {
    Verdict.FIXED_ALL: ("green", "verified: the corrected source compiles with no errors"),
    Verdict.FIXED_TARGET: ("yellow", "partly verified: this error is gone, others remain"),
    Verdict.NO_IMPROVEMENT: ("red", "NOT verified: the error is still reported"),
    Verdict.WORSE: ("red", "NOT verified: the fix introduces more errors"),
    Verdict.INVALID_EDIT: ("red", "NOT verified: the edit could not be applied"),
    Verdict.NO_EDIT: ("yellow", "no concrete fix was proposed, nothing to verify"),
}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scompiler", description="Fault-tolerant compiler front end with AI explanations."
    )
    p.add_argument("file", nargs="?", help="source file to compile, or '-' for stdin")
    p.add_argument("--explain", action="store_true",
                   help="ask the AI to explain errors and propose validated fixes")
    p.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")
    p.add_argument("--max-diagnostics", type=int, default=3, metavar="N",
                   help="explain at most N errors, in source order (default 3; later ones are "
                        "often cascades and each costs an API call)")
    p.add_argument("--max-attempts", type=int, default=3, metavar="N",
                   help="retries per error when a suggestion fails validation (default 3)")
    p.add_argument("--provider", choices=PROVIDERS, default="auto",
                   help="AI backend (default auto: Gemini if GEMINI_API_KEY is set, "
                        "else Anthropic if ANTHROPIC_API_KEY is set)")
    p.add_argument("--model", default=None, help="model name (default: $SCOMPILER_MODEL)")
    p.add_argument("--list-models", action="store_true",
                   help="list Gemini models your key can use, then exit (no file needed)")
    p.add_argument("--no-color", action="store_true", help="disable colored output")
    return p


def _default_client_factory(provider: str, model: Optional[str]) -> AIClient:
    return resolve_client(provider, model)


def _read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _render_explanation(con: Console, source: str, exp: Explanation) -> None:
    d = exp.diagnostic
    con.print(f"[bold]AI analysis — line {d.line}, column {d.column}[/bold]  ({d.code})",
              highlight=False)
    if exp.response is None:
        con.print(f"  [red]No usable AI answer:[/red] {exp.error}", highlight=False)
        con.print()
        return
    r, v = exp.response, exp.validation
    con.print(f"  [bold]Probable cause:[/bold] {r.probable_cause}", highlight=False)
    con.print(f"  [bold]Explanation:[/bold]    {r.explanation}", highlight=False)
    con.print(f"  [bold]Suggested fix:[/bold]  {r.suggested_correction}", highlight=False)
    if v is not None and v.corrected_source is not None:
        diff = list(difflib.unified_diff(
            source.splitlines(), v.corrected_source.splitlines(),
            "original", "corrected", lineterm="", n=1,
        ))
        for line in diff[2:]:  # skip ---/+++ header
            style = "green" if line.startswith("+") else "red" if line.startswith("-") else "dim"
            con.print(f"      {line}", style=style, markup=False, highlight=False)
    if v is not None:
        color, text = _VERDICT_TEXT[v.verdict]
        con.print(f"  [bold]Validation:[/bold]     [{color}]{text}[/{color}]", highlight=False)
        if v.destructive:
            con.print(f"  [red]Warning:[/red] fix removes {v.tokens_removed} tokens; "
                      "it may be deleting code rather than repairing it.", highlight=False)
    if v is not None and v.invented:
        con.print(f"  [yellow]Caution:[/yellow] the fix introduces {', '.join(v.invented)}, "
                  "which you never wrote. It parses, but it is a guess.", highlight=False)
    con.print(
        f"  [bold]Confidence:[/bold]     {exp.label} ({exp.confidence:.2f}; "
        f"model claimed {r.confidence:.2f}; {exp.attempts} attempt(s))",
        highlight=False,
    )
    con.print()


def main(
    argv: Optional[List[str]] = None,
    client_factory: Optional[ClientFactory] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the CLI. Exit code: 0 = compiled cleanly, 1 = source has errors, 2 = usage/IO error."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_models:
        try:
            for name in GeminiClient().list_models():
                print(name, file=out)
        except AIUnavailable as exc:
            print(f"scompiler: {exc}", file=err)
            return 2
        return 0
    if args.file is None:
        parser.error("the following arguments are required: file")

    try:
        source = _read_source(args.file)
    except OSError as exc:
        print(f"scompiler: cannot read {args.file!r}: {exc.strerror or exc}", file=err)
        return 2

    result = parse_source(source)
    errors = [d for d in result.diagnostics if d.is_error]
    color = not args.no_color and not args.as_json and out.isatty()
    con = Console(file=out, force_terminal=color, no_color=not color, highlight=False, width=100)
    exit_code = 0 if result.success else 1

    explanations: List[Explanation] = []
    ai_note: Optional[str] = None
    if args.explain and errors:
        try:
            client = (client_factory or _default_client_factory)(args.provider, args.model)
        except AIUnavailable as exc:
            ai_note = f"AI explanations unavailable: {exc}. Showing the standard report."
        else:
            for diag in errors[: max(0, args.max_diagnostics)]:
                explanations.append(
                    explain_diagnostic(source, diag, errors, client, args.max_attempts)
                )

    if args.as_json:
        payload = {
            "success": result.success,
            "errors": [
                {"code": d.code, "category": d.category, "line": d.line, "column": d.column,
                 "message": d.message, "suggestion": d.suggestion}
                for d in errors
            ],
            "explanations": [e.to_dict() for e in explanations],
            "ai_note": ai_note,
        }
        out.write(json.dumps(payload, indent=2) + "\n")
        return exit_code

    out.write(result.get_report(color=color, show_source=True))
    if ai_note:
        print(f"\nnote: {ai_note}", file=err)
    if explanations:
        out.write("\n")
        for exp in explanations:
            _render_explanation(con, source, exp)
        skipped = len(errors) - len(explanations)
        if skipped > 0:
            con.print(f"[dim]{skipped} more error(s) not explained "
                      f"(raise --max-diagnostics; fixing the first often clears the rest).[/dim]")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
