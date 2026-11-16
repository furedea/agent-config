"""Without ast-grep, comments cannot be told from strings, so a change that may turn a marker into a comment asks."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_unparsed")


@pytest.fixture(autouse=True)
def no_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")


def decide(tool: str, values: dict) -> str:
    return guard.decide({"tool_name": tool, "tool_input": values}).decision


def test_moving_a_marker_line_out_of_a_yaml_block_scalar_asks(tmp_path: Path) -> None:
    target = tmp_path / "ci.yml"
    target.write_text("key: |\n  # ast-grep-ignore: rule\nnext: 1\n")
    values = {"file_path": str(target), "old_string": "  # ast-grep-ignore", "new_string": "# ast-grep-ignore"}
    assert decide("Edit", values) == "ask"


def test_inserting_a_heredoc_terminator_above_a_marker_asks(tmp_path: Path) -> None:
    """A terminator is a bare word, so nothing in the inserted line shows that it ends a string."""
    target = tmp_path / "run.sh"
    target.write_text("cat <<EOF\n# ast-grep-ignore: rule\nEOF\necho hi\n")
    values = {"path": str(target), "command": "insert", "insert_line": 1, "new_str": "EOF"}
    assert decide("Edit", values) == "ask"


def test_editing_a_script_without_a_heredoc_away_from_a_marker_passes(tmp_path: Path) -> None:
    target = tmp_path / "run.sh"
    target.write_text("# shellcheck disable=SC2086\necho $x\necho hi\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "echo hi", "new_string": "echo bye"}) == "allow"
