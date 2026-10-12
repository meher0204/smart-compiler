"""Guards the example set: the valid file compiles, every flawed file does not."""

import importlib.util
from pathlib import Path

import pytest

from scompiler.ai import ScriptedClient
from scompiler.parser import parse_source

EXAMPLES = Path(__file__).parent.parent / "examples"
FILES = sorted(EXAMPLES.glob("*.src"))


def test_example_set_is_present():
    assert len(FILES) >= 15


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_example_compiles_only_if_valid(path):
    ok = parse_source(path.read_text()).success
    assert ok == path.name.startswith("00_valid")


def load_runner(tmp_path, monkeypatch, names=None):
    spec = importlib.util.spec_from_file_location("run_examples", EXAMPLES / "run_examples.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "HERE", tmp_path)
    for f in FILES:
        if names is None or f.name[:2] in names:
            (tmp_path / f.name).write_text(f.read_text())
    return mod


NO_EDIT_REPLY = (
    '{"probable_cause": "c", "explanation": "e", "suggested_correction": "s", '
    '"confidence": 0.5, "edit": null}'
)


def test_runner_saves_progress_and_resumes(tmp_path, monkeypatch):
    mod = load_runner(tmp_path, monkeypatch, names={"00", "01", "02", "04"})
    client = ScriptedClient([NO_EDIT_REPLY])
    assert mod.main(["--delay", "0", "--only", "01"], client=client) == 0
    calls_after_first = len(client.calls)
    assert calls_after_first >= 1

    # second pass over everything: 01 is skipped, 02 and 04 are new, 01's result is kept
    assert mod.main(["--delay", "0", "--resume"], client=client) == 0
    csv_text = (tmp_path / "results.csv").read_text()
    assert "01_missing_semicolon.src" in csv_text and "04_missing_semicolon_return.src" in csv_text
    # 01 was skipped; 02 and 04 each cost the same number of calls as 01 did
    assert len(client.calls) == calls_after_first * 3


def test_runner_stops_cleanly_on_rate_limit(tmp_path, monkeypatch):
    from scompiler.ai import AIUnavailable

    class Limited:
        def complete(self, system, messages):
            raise AIUnavailable("Gemini API error: rate limit hit")

    mod = load_runner(tmp_path, monkeypatch, names={"01", "02", "04"})
    assert mod.main(["--delay", "0"], client=Limited()) == 3
    rows = (tmp_path / "results.csv").read_text().splitlines()
    assert len(rows) == 3  # header + the 2 files processed before it stopped; progress was saved


def test_runner_works_offline_and_with_scripted_client(tmp_path, monkeypatch):
    mod = load_runner(tmp_path, monkeypatch, names={"00", "01", "02"})

    assert mod.main(["--no-ai"]) == 0
    assert "rule_suggestion" in (tmp_path / "results.md").read_text()

    assert mod.main(["--delay", "0"], client=ScriptedClient([NO_EDIT_REPLY])) == 0
    assert "no_edit" in (tmp_path / "results.csv").read_text()
