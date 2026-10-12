"""Tests for the AI module, validator and CLI. No network: the model is scripted."""

import io
import json

import pytest

from scompiler.ai import (
    AIResponseError,
    Edit,
    ScriptedClient,
    Verdict,
    apply_edit,
    combine_confidence,
    explain_diagnostic,
    parse_response,
    validate_edit,
)
from scompiler.ai.client import AIUnavailable
from scompiler.cli import main
from scompiler.parser import parse_source

BROKEN = "int main() {\n    int x = 10\n    int y = 20;\n    return x + y;\n}\n"
CLEAN = "int main() {\n    int x = 10;\n    int y = 20;\n    return x + y;\n}\n"


def reply(edit="default", confidence=0.9):
    if edit == "default":
        edit = {"start_line": 2, "end_line": 2, "replacement": "    int x = 10;"}
    return json.dumps({
        "probable_cause": "Missing semicolon after the declaration of x.",
        "explanation": "Statements must end with ';'.",
        "suggested_correction": "Add ';' after 10.",
        "confidence": confidence,
        "edit": edit,
    })


def first_error(src=BROKEN):
    errs = [d for d in parse_source(src).diagnostics if d.is_error]
    return errs[0], errs


# ---- schema ----------------------------------------------------------------
def test_parse_response_plain_and_fenced():
    assert parse_response(reply()).edit == Edit(2, 2, "    int x = 10;")
    fenced = "Sure!\n```json\n" + reply() + "\n```"
    assert parse_response(fenced).confidence == 0.9


def test_parse_response_clamps_and_converts_confidence():
    assert parse_response(reply(confidence=87)).confidence == 0.87
    assert parse_response(reply(confidence=-3)).confidence == 0.0


@pytest.mark.parametrize("bad", ["not json", "[1, 2]", '{"probable_cause": "x"}'])
def test_parse_response_rejects_garbage(bad):
    with pytest.raises(AIResponseError):
        parse_response(bad)


def test_null_edit_allowed():
    assert parse_response(reply(edit=None)).edit is None


# ---- apply_edit / validator ------------------------------------------------
def test_apply_edit_replace_insert_delete():
    src = "a\nb\nc"
    assert apply_edit(src, Edit(2, 2, "B")) == "a\nB\nc"
    assert apply_edit(src, Edit(2, 1, "new")) == "a\nnew\nb\nc"
    assert apply_edit(src, Edit(2, 2, "")) == "a\nc"


def test_apply_edit_bounds():
    from scompiler.ai.validator import EditError

    with pytest.raises(EditError):
        apply_edit("a\nb", Edit(9, 9, "x"))
    with pytest.raises(EditError):
        apply_edit("a\nb", Edit(1, 5, "x"))


def test_validate_good_fix():
    target, errs = first_error()
    v = validate_edit(BROKEN, target, Edit(2, 2, "    int x = 10;"), baseline_errors=len(errs))
    assert v.verdict is Verdict.FIXED_ALL and v.accepted
    assert v.corrected_source == CLEAN.rstrip("\n") + "\n"


def test_validate_fix_in_wrong_place_is_rejected():
    target, errs = first_error()
    v = validate_edit(BROKEN, target, Edit(4, 4, "    return x + y;;"), baseline_errors=len(errs))
    assert not v.accepted


def test_validate_no_edit_and_invalid_edit():
    target, _ = first_error()
    assert validate_edit(BROKEN, target, None).verdict is Verdict.NO_EDIT
    assert validate_edit(BROKEN, target, Edit(99, 99, "x")).verdict is Verdict.INVALID_EDIT


def test_destructive_fix_is_flagged_even_though_it_parses():
    target, _ = first_error()
    v = validate_edit(BROKEN, target, Edit(1, 5, "int main() {\n}"))  # deletes the body
    assert v.verdict is Verdict.FIXED_ALL
    assert v.destructive and not v.accepted


# ---- confidence ------------------------------------------------------------
def test_validation_dominates_model_confidence():
    target, errs = first_error()
    good = validate_edit(BROKEN, target, Edit(2, 2, "    int x = 10;"), len(errs))
    bad = validate_edit(BROKEN, target, None, len(errs))
    assert combine_confidence(0.2, good) >= 0.5
    assert combine_confidence(1.0, bad) <= 0.2
    assert combine_confidence(1.0, None) <= 0.1


# ---- explain loop ----------------------------------------------------------
def test_explain_first_try():
    target, errs = first_error()
    client = ScriptedClient([reply()])
    exp = explain_diagnostic(BROKEN, target, errs, client)
    assert exp.attempts == 1 and exp.validation.accepted and exp.label == "high"


def test_explain_retries_after_bad_json_and_bad_fix():
    target, errs = first_error()
    client = ScriptedClient(["I think it's a semicolon", reply(edit=None), reply()])
    exp = explain_diagnostic(BROKEN, target, errs, client, max_attempts=3)
    assert exp.attempts == 3 and exp.validation.accepted
    # the retry prompt told the model why it was rejected
    assert "rejected" in client.calls[1][-1]["content"]


def test_explain_gives_up_but_returns_best_attempt():
    target, errs = first_error()
    wrong = reply(edit={"start_line": 4, "end_line": 4, "replacement": "    return x;"})
    exp = explain_diagnostic(BROKEN, target, errs, ScriptedClient([wrong]), max_attempts=2)
    assert exp.response is not None and not exp.validation.accepted and exp.label == "low"


def test_explain_survives_transport_failure():
    class Down:
        def complete(self, system, messages):
            raise AIUnavailable("offline")

    target, errs = first_error()
    exp = explain_diagnostic(BROKEN, target, errs, Down())
    assert exp.response is None and exp.error == "offline"


# ---- CLI -------------------------------------------------------------------
def run_cli(tmp_path, source, *flags, client=None):
    f = tmp_path / "prog.src"
    f.write_text(source)
    out, err = io.StringIO(), io.StringIO()
    factory = (lambda provider, model: client) if client else None
    code = main([str(f), *flags], client_factory=factory, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_cli_clean_file_exit_zero(tmp_path):
    code, out, _ = run_cli(tmp_path, CLEAN)
    assert code == 0 and "no errors" in out


def test_cli_without_explain_never_calls_ai(tmp_path):
    client = ScriptedClient([reply()])
    code, out, _ = run_cli(tmp_path, BROKEN, client=client)
    assert code == 1 and client.calls == []


def test_cli_explain_shows_validated_fix(tmp_path):
    client = ScriptedClient([reply()])
    code, out, _ = run_cli(tmp_path, BROKEN, "--explain", "--no-color", client=client)
    assert code == 1
    assert "Probable cause" in out and "verified" in out and "+    int x = 10;" in out


def test_cli_json(tmp_path):
    client = ScriptedClient([reply()])
    code, out, _ = run_cli(tmp_path, BROKEN, "--explain", "--json", client=client)
    data = json.loads(out)
    assert data["success"] is False
    assert data["explanations"][0]["validation"]["verdict"] == "fixed_all"


def test_cli_missing_api_key_falls_back_to_report(tmp_path, monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    code, out, err = run_cli(tmp_path, BROKEN, "--explain")
    assert code == 1 and "ERROR REPORT" in out and "unavailable" in err


def test_cli_missing_file_exit_two(tmp_path):
    err = io.StringIO()
    assert main([str(tmp_path / "nope.src")], stdout=io.StringIO(), stderr=err) == 2


# ---- invented values ---------------------------------------------------------
def test_invented_literal_is_flagged_and_capped():
    src = "int main() {\n    int x = ;\n    return x;\n}\n"
    target, errs = first_error(src)
    v = validate_edit(src, target, Edit(2, 2, "    int x = 0;"), baseline_errors=len(errs))
    assert v.verdict is Verdict.FIXED_ALL and v.invented == ["0"]
    assert combine_confidence(0.97, v) <= 0.40


def test_faithful_fixes_are_not_flagged():
    # missing semicolon: nothing new
    target, errs = first_error()
    v = validate_edit(BROKEN, target, Edit(2, 2, "    int x = 10;"), baseline_errors=len(errs))
    assert v.invented == []
    # keyword typo: adds the keyword `float`, which is not a value
    typo = "int main() {\n    flaot y = 3.5;\n    return 0;\n}\n"
    target, errs = first_error(typo)
    v = validate_edit(typo, target, Edit(2, 2, "    float y = 3.5;"), baseline_errors=len(errs))
    assert v.invented == [] and v.verdict is Verdict.FIXED_ALL
    # = -> == adds an operator, not a value
    cond = (
        "int main() {\n    int x = 5;\n    if (x = 5) {\n        return 1;\n    }\n"
        "    return 0;\n}\n"
    )
    target, errs = first_error(cond)
    v = validate_edit(cond, target, Edit(3, 3, "    if (x == 5) {"), baseline_errors=len(errs))
    assert v.invented == []


def test_reusing_existing_values_is_not_invented():
    src = "int main() {\n    int x = 5;\n    int y = ;\n    return y;\n}\n"
    target, errs = first_error(src)
    v = validate_edit(src, target, Edit(3, 3, "    int y = x;"), baseline_errors=len(errs))
    assert v.invented == []


def test_cli_warns_about_invented_value(tmp_path):
    src = "int main() {\n    int x = ;\n    return x;\n}\n"
    edit = {"start_line": 2, "end_line": 2, "replacement": "    int x = 0;"}
    client = ScriptedClient([reply(edit=edit, confidence=0.97)])
    code, out, _ = run_cli(tmp_path, src, "--explain", "--no-color", client=client)
    assert "Caution" in out and "low" in out
