"""Every comment scan of one decision shares one time budget that fits the hook timeout, and running out asks."""

import time
from pathlib import Path

import pytest
from tests.runtime import StubWriter, load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_budget")
comment_nodes = guard.comment_nodes

HANG = """
    import time
    time.sleep(60)
"""


def test_the_budget_fits_the_hook_timeout() -> None:
    assert comment_nodes.BUDGET_SECONDS <= 20


def test_a_hanging_scanner_ends_the_decision_within_the_budget_and_asks(
    tmp_path: Path, executable: StubWriter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A move judges the source and destination before and after the edit, so the scans would add up without it."""
    executable("ast-grep", HANG)
    monkeypatch.setattr(comment_nodes, "BUDGET_SECONDS", 1)
    source = tmp_path / "app.py"
    source.write_text("x = 1  # noqa: E501\nfoo()\n")
    patch = "\n".join(
        (
            "*** Begin Patch",
            f"*** Update File: {source}",
            f"*** Move to: {tmp_path / 'app.rs'}",
            "@@",
            "-foo()",
            "+bar()",
            "*** End Patch",
        )
    )
    started = time.monotonic()
    verdict = guard.decide({"tool_name": "apply_patch", "tool_input": {"patch": patch}})
    assert time.monotonic() - started < 5
    assert verdict.decision == "ask"


def test_a_scan_out_of_budget_is_unknown_and_the_next_decision_scans_again() -> None:
    comment_nodes.start_budget(0)
    assert comment_nodes.comment_spans("x = 1  # a\n", ".py") is None
    assert comment_nodes.budget_ran_out()
    comment_nodes.start_budget()
    assert comment_nodes.comment_spans("x = 1  # a\n", ".py") == [(7, 10)]
    assert not comment_nodes.budget_ran_out()


@pytest.mark.parametrize(
    "name,text",
    [
        ("app.py", "x = 1  # noqa: E501\n" * 20000),
        ("app.ts", "/*\n" + "eslint-disable no-console\n" * 20000 + "*/\n"),
        ("lib.rs", "#[allow(dead_code,\n" * 5000),
    ],
    ids=["many line comments", "many markers in one block comment", "many unclosed attributes"],
)
def test_a_file_with_many_markers_is_judged_well_within_the_hook_timeout(name: str, text: str) -> None:
    """The work after the scans grows with the file, not with markers times lines, so it cannot time the hook out."""
    values = {"file_path": f"/nonexistent/{name}", "content": text}
    started = time.monotonic()
    verdict = guard.decide({"tool_name": "Write", "tool_input": values})
    assert time.monotonic() - started < 5
    assert verdict.decision == "ask"
