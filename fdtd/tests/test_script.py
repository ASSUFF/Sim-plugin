from pathlib import Path

import pytest

from lumerical_fdtd.engine import (
    ScriptError,
    eval_script,
    flatten_matrix_literals,
    script_statements,
    substitute_assignments,
)


def test_script_assignment_rewrites_one_variable() -> None:
    script = "L_mmi = 11e-6;\nW = 1.5e-6;\n"
    changed = substitute_assignments(script, {"L_mmi": 12.5e-6})
    assert changed.startswith("L_mmi = 1.25e-05;")
    assert "W = 1.5e-6;" in changed
    with pytest.raises(ValueError, match="没有赋值"):
        substitute_assignments(script, {"missing": 1})


def test_multiline_matrix_is_one_statement_and_one_line() -> None:
    script = 'set("vertices", [\n  -7.0e-6,  0.25e-6;\n  -4.35e-6, 0.25e-6;\n]);\naddrect;\n'
    statements = script_statements(script)
    assert [item["line"] for item in statements] == [1, 5]
    flat = flatten_matrix_literals(statements[0]["text"])
    assert "\n" not in flat
    assert "-7.0e-6,  0.25e-6;" in flat
    assert flat.endswith(");")


def test_braced_loop_stays_one_statement() -> None:
    script = "for(i=1:N) {\n    t = (i-1)/(N-1);\n    verts(i,1) = t;\n}\naddpoly;\n"
    statements = script_statements(script)
    assert len(statements) == 2
    assert statements[0]["line"] == 1
    assert "verts(i,1)" in statements[0]["text"]
    assert statements[1]["text"] == "addpoly;"


def test_comment_and_string_semicolon_do_not_split() -> None:
    script = 'a = "p;q"; # keep\nb = 2;\n'
    statements = script_statements(script)
    assert [item["text"] for item in statements] == ['a = "p;q";', "b = 2;"]
    assert statements[1]["line"] == 2


def test_crossing_script_keeps_each_loop_together() -> None:
    script = Path(__file__).resolve().parents[1].joinpath("examples", "crossing_sin.lsf").read_text(encoding="utf-8")
    statements = script_statements(script)
    loops = [item for item in statements if item["text"].startswith("for(")]
    assert len(loops) == 4
    assert all("verts(i,1)" in item["text"] for item in loops)
    assert all("addrect" not in item["text"] for item in loops)


class _Session:
    def __init__(self, fail_on):
        self.fail_on = fail_on
        self.seen = []

    def eval(self, text):
        self.seen.append(text)
        if self.fail_on in text:
            raise RuntimeError("Failed to evaluate code")


def test_eval_reports_the_failing_statement() -> None:
    session = _Session("bad")
    script = "a = 1;\nbad = 2;\nc = 3;\n"
    with pytest.raises(ScriptError) as caught:
        eval_script(session, script)
    assert caught.value.index == 2
    assert caught.value.line == 2
    assert "Failed to evaluate code" in str(caught.value.cause)
    assert session.seen == ["a = 1;", "bad = 2;"]


def test_eval_sends_a_matrix_as_one_line() -> None:
    session = _Session("never")
    script = 'set("vertices", [\n  1, 2;\n  3, 4;\n]);\n'
    eval_script(session, script)
    assert len(session.seen) == 1
    assert "\n" not in session.seen[0]
    assert "1, 2;" in session.seen[0]
    assert "3, 4;" in session.seen[0]
