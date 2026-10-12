"""Run every examples/*.src and tabulate rule-based suggestion vs AI result.

    python examples/run_examples.py --no-ai          # offline: rule-based columns only
    python examples/run_examples.py                  # + AI (needs an API key set)
    python examples/run_examples.py --resume         # skip files that already have an AI result
    python examples/run_examples.py --only 05 06     # just files whose name starts with 05, 06

Results are saved after EVERY file and merged into any existing results.csv, so a rate-limit
crash or Ctrl-C loses nothing: wait a bit, then rerun with --resume.

The last column, "human_judgment", is left blank on purpose: the validator can only tell you the
fix *parses*, only you can say whether it is what a programmer would actually write.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from scompiler import parse_source
from scompiler.ai import AIClient, AIUnavailable, explain_diagnostic, resolve_client

HERE = Path(__file__).parent
RULE_COLS = ["file", "errors", "first_error", "rule_suggestion"]
AI_COLS = ["ai_verdict", "ai_attempts", "ai_confidence", "ai_fix", "ai_edit"]
COLUMNS = RULE_COLS + AI_COLS + ["human_judgment"]
MAX_RATE_LIMIT_FAILURES = 2


def load_existing(out_dir: Path) -> Dict[str, Dict[str, Any]]:
    path = out_dir / "results.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["file"]: {c: r.get(c, "") for c in COLUMNS} for r in csv.DictReader(fh)}


def write_outputs(rows: Dict[str, Dict[str, Any]], out_dir: Path) -> None:
    ordered = [rows[k] for k in sorted(rows)]
    with open(out_dir / "results.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(ordered)
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in ordered:
        cells = [str(r[c]).replace("|", "\\|").replace("\n", " ") for c in COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    (out_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def has_ai_result(row: Dict[str, Any]) -> bool:
    verdict = str(row.get("ai_verdict", ""))
    return bool(verdict) and not verdict.startswith("no answer")


def run(
    files: List[Path],
    client: Optional[AIClient],
    delay: float,
    max_attempts: int,
    out_dir: Path,
    resume: bool = False,
) -> int:
    rows = load_existing(out_dir)
    rate_failures = 0
    try:
        for path in files:
            old = rows.get(path.name, {c: "" for c in COLUMNS})
            if client is not None and resume and has_ai_result(old):
                print(f"{path.name:40} skipped (already has an AI result)", flush=True)
                continue

            source = path.read_text(encoding="utf-8")
            errors = [d for d in parse_source(source).diagnostics if d.is_error]
            row = {c: old.get(c, "") for c in COLUMNS}  # keep earlier AI/human columns
            row["file"], row["errors"] = path.name, len(errors)
            status = ""
            if not errors:
                row["first_error"], row["rule_suggestion"] = "(compiles cleanly)", ""
                status = "compiles cleanly"
            else:
                first = errors[0]
                row["first_error"] = f"L{first.line}:{first.column} {first.code}"
                row["rule_suggestion"] = first.suggestion or "(none)"
                status = row["first_error"]
                if client is not None:
                    exp = explain_diagnostic(source, first, errors, client, max_attempts)
                    if exp.response is None:
                        row["ai_verdict"] = f"no answer: {exp.error}"
                        for c in ("ai_attempts", "ai_confidence", "ai_fix", "ai_edit"):
                            row[c] = ""
                        rate_failures = rate_failures + 1 if "rate limit" in str(exp.error) else 0
                    else:
                        rate_failures = 0
                        row["ai_verdict"] = exp.validation.verdict.value
                        row["ai_attempts"] = exp.attempts
                        row["ai_confidence"] = f"{exp.label} ({exp.confidence:.2f})"
                        if exp.validation.invented:
                            names = ", ".join(exp.validation.invented)
                            row["ai_confidence"] += f" [invented: {names}]"
                        if exp.validation.destructive:
                            row["ai_confidence"] += " [large edit]"
                        row["ai_fix"] = exp.response.suggested_correction
                        e = exp.response.edit
                        row["ai_edit"] = (
                            "" if e is None
                            else f"L{e.start_line}-{e.end_line}: {e.replacement.strip()}"
                        )
                    status = row["ai_verdict"]
            rows[path.name] = row
            write_outputs(rows, out_dir)  # save after every file
            print(f"{path.name:40} {status}", flush=True)

            if rate_failures >= MAX_RATE_LIMIT_FAILURES:
                print(
                    "\nRate limit reached. Progress is saved. Wait a few minutes (or until "
                    "tomorrow if it is a daily limit), then rerun with --resume.",
                    file=sys.stderr,
                )
                return 3
            if client is not None and errors:
                time.sleep(delay)  # stay under free-tier requests-per-minute limits
    except KeyboardInterrupt:
        write_outputs(rows, out_dir)
        print("\nInterrupted. Progress saved; rerun with --resume to continue.", file=sys.stderr)
        return 130
    print(f"\nWrote {out_dir / 'results.md'} and {out_dir / 'results.csv'}")
    return 0


def main(argv: Optional[List[str]] = None, client: Optional[AIClient] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--no-ai", action="store_true", help="skip the AI columns")
    ap.add_argument("--resume", action="store_true", help="skip files that already have AI results")
    ap.add_argument("--only", nargs="*", metavar="PREFIX", help="only files starting with these")
    ap.add_argument("--delay", type=float, default=15.0,
                    help="seconds between AI calls (default 15; free tiers are often ~5-10/min)")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--provider", default="auto", choices=["auto", "gemini", "anthropic"])
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    files = sorted(HERE.glob("*.src"))
    if args.only:
        files = [f for f in files if f.name.startswith(tuple(args.only))]
    if not files:
        print("no matching .src files", file=sys.stderr)
        return 2

    if args.no_ai:
        client = None
    elif client is None:
        try:
            client = resolve_client(args.provider, args.model)
        except AIUnavailable as exc:
            print(f"AI unavailable ({exc}); running rule-based columns only.", file=sys.stderr)

    return run(files, client, args.delay, args.max_attempts, HERE, args.resume)


if __name__ == "__main__":
    raise SystemExit(main())
