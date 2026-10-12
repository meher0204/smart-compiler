# Test set

17 small programs, one deliberate flaw each (except where noted). Run them all:

    python examples/run_examples.py --no-ai     # offline, rule-based column only
    python examples/run_examples.py             # + AI column (needs an API key)

Then fill in the `human_judgment` column of `results.md` yourself.

| File | Flaw | What it tests |
|---|---|---|
| 00_valid | none | control: must compile cleanly |
| 01-04 | missing `;` / `)` / `}` | easy: rule-based suggestions should already be right; AI should match |
| 03_missing_rbrace | `}` missing | error is reported at EOF, far from the real mistake; where the `}` belongs is ambiguous |
| 05_assign_in_condition | `if (x = 5)` | rule-based says "insert `)`" which is **wrong**; correct fix is `==` |
| 06_keyword_typo | `flaot` | rule-based says "insert `;`" which is **wrong**; correct fix is `float` |
| 07_illegal_character | `@` | lexical error plus a cascade; any fix must guess the intended operator (not detectable by the invented-value check: the lexer drops `@`) |
| 08_unsupported_for_loop | `for` | language has no `for`; sensible fix is rewriting as `while`, a large edit |
| 09_unsupported_string | `printf("hello")` | language has no strings; no fix keeps the intent, so expect a weak or failed fix |
| 10, 11 | `int x = ;` / `5 +;` | intended value is unknowable: tests honest (low) confidence |
| 12_unsupported_and_operator | `&&` | 4 errors from one mistake (two lexical + cascades) |
| 13_two_independent_errors | 2 missing `;` | one edit may span several lines, so a single answer can clear both (`fixed_all`) |
| 14_cascade | missing `)` plus missing `;` | two real errors in different places |
| 15_function_param_error | `int a, b` | 5 errors from one mistake: shows cascade noise |
| 16_missing_closing_brace_eof | `}` missing at EOF | easy brace case |

What to look for when you present: a hard case the AI fixes and the rules don't (05, 06),
a first attempt that fails validation and a retry that succeeds, and a case where the AI is
wrong or unsure (09, 10). Report failures honestly; they are results.
