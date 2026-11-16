"""A suppression cannot reach the user's review through apply_patch: a move, an inexact hunk, or a file named twice."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_patch")


def decide(tool: str, values: dict) -> str:
    return guard.decide({"tool_name": tool, "tool_input": values}).decision


def test_a_patch_that_moves_a_file_into_code_and_adds_a_suppression_asks() -> None:
    patch = (
        "*** Begin Patch\n*** Update File: docs/notes.md\n*** Move to: src/notes.py\n@@\n-x = 1\n"
        "+x = 1  # ast-grep-ignore\n*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_file_whose_existing_markers_take_effect_at_the_destination_asks(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# ast-grep-ignore\nx = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'notes.py'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_code_file_with_its_existing_markers_passes(tmp_path: Path) -> None:
    source = tmp_path / "old.py"
    source.write_text("x = 1  # noqa: E501\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'new.py'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


def test_a_patch_hunk_beside_a_top_marker_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nbad()\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n # ast-grep-ignore: rule_a\n+\n bad()\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_to_a_file_without_an_ast_grep_marker_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\nbad()  # noqa: E501\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-x = 1\n+x = 2\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


@pytest.mark.parametrize(
    "hunk", ["@@\n+\n bad()", "@@ bad()\n+\n bad()"], ids=["context on the second line", "anchor on the second line"]
)
def test_a_patch_hunk_anchored_below_a_top_marker_asks(tmp_path: Path, hunk: str) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nbad()\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n{hunk}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_that_removes_the_lines_above_a_marker_asks(tmp_path: Path) -> None:
    """Deleting the first line can move a marker followed by a blank line to the top, where it covers the file."""
    target = tmp_path / "app.py"
    target.write_text("x = 1\n# ast-grep-ignore: rule_a\n\nbad()\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-x = 1\n # ast-grep-ignore: rule_a\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_file_between_extensions_where_its_markers_already_apply_passes(tmp_path: Path) -> None:
    source = tmp_path / "tool.py"
    source.write_text("x = 1  # noqa: E501\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'tool.pyi'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


@pytest.mark.parametrize(
    "source_name,text",
    [
        ("tool.ts", "x()\n// ast-grep-ignore: rule_a\nbad()\n"),
        ("tool.py", "x = 1\n# ast-grep-ignore: rule_a\nbad()\n"),
    ],
    ids=["a comment in both", "not a comment at the destination"],
)
def test_moving_an_ast_grep_marker_between_code_extensions_passes(tmp_path: Path, source_name: str, text: str) -> None:
    source = tmp_path / source_name
    source.write_text(text)
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'tool.go'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


@pytest.mark.parametrize(
    "source_name,text,destination_name",
    [
        ("tool.go", "# ast-grep-ignore\nbad()\n", "tool.py"),
        ("tool.py", 'DOC = """\n// ast-grep-ignore\n"""\n', "tool.go"),
    ],
    ids=["not a comment in Go, a comment in Python", "inside a Python string, a comment in Go"],
)
def test_a_move_that_turns_an_inert_marker_into_a_comment_asks(
    tmp_path: Path, source_name: str, text: str, destination_name: str
) -> None:
    source = tmp_path / source_name
    source.write_text(text)
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / destination_name}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_marker_out_of_a_heredoc_into_python_asks(tmp_path: Path) -> None:
    source = tmp_path / "run.sh"
    source.write_text("cat <<EOF\n# ast-grep-ignore: rule\nEOF\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'run.py'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_that_turns_a_context_line_into_a_comment_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.ts"
    target.write_text("const text = `\n// @ts-ignore\n`;\nfoo(1);\n")
    hunk = "@@\n-const text = `\n // @ts-ignore\n-`;\n foo(1)"
    patch = f"*** Begin Patch\n*** Update File: {target}\n{hunk};\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_far_from_the_markers_of_a_file_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nbad()\n\n\nx = 1  # noqa: E501\ny = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-y = 1\n+y = 2\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


def test_a_patch_that_does_not_match_a_file_with_a_suppression_exactly_asks(tmp_path: Path) -> None:
    """The applier also matches context loosely, so where such a hunk lands is unknown and the guard fails closed."""
    target = tmp_path / "app.py"
    target.write_text("x = 1  # noqa: E501\ny = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-y  =  1\n+y = 2\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_an_add_file_patch_over_an_existing_file_is_judged_as_its_new_text(tmp_path: Path) -> None:
    """Adding a file replaces it, so its old text does not cancel a marker the new text adds."""
    target = tmp_path / "app.py"
    target.write_text("x = 1  # noqa: E501\n")
    patch = f"*** Begin Patch\n*** Add File: {target}\n+y = 2  # noqa: E501\n+z = 3  # noqa: E501\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


@pytest.mark.parametrize(
    "hunk",
    ["@@\n-y = 1\n+y = 2\n*** End of File", "@@\n-y = 1\n+y = 2\nnot a hunk line", "@@\n-x = 1\n+x = 2"],
    ids=["end of file marker", "unknown line", "matches more than once"],
)
def test_a_patch_the_guard_cannot_place_exactly_in_a_file_with_a_suppression_asks(tmp_path: Path, hunk: str) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\nz = 1  # noqa: E501\nx = 1\ny = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n{hunk}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_an_empty_line_in_a_hunk_is_an_empty_context_line(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("z = 1  # noqa: E501\n\ny = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n z = 1  # noqa: E501\n\n-y = 1\n+y = 2\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "allow"


def test_moving_a_file_where_a_nolint_becomes_a_comment_asks(tmp_path: Path) -> None:
    source = tmp_path / "tool.py"
    source.write_text("f() // nolint\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'tool.go'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_that_names_one_file_twice_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    patch = (
        f"*** Begin Patch\n*** Update File: {target}\n@@\n-x = 1\n+x = 2\n"
        f"*** Add File: {target}\n+x = 2\n*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_marker_that_is_a_comment_only_in_the_middle_of_the_moved_file_asks(tmp_path: Path) -> None:
    """A carried marker counts by itself, not by how its line parses when cut out of the file."""
    source = tmp_path / "tool.py"
    source.write_text('x = 1\ns = """\n"""  // nolint\n')
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'tool.go'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


@pytest.mark.parametrize(
    "second",
    [
        "*** Add File: {dir}/./app.py\n+x = 2\n",
        "*** Add File: {dir}/APP.py\n+x = 2\n",
        "*** Update File: {dir}/other.py\n*** Move to: {dir}/app.py\n",
    ],
    ids=["same file through another spelling", "same file in another case", "another file moved onto it"],
)
def test_a_patch_that_reaches_one_file_twice_asks(tmp_path: Path, second: str) -> None:
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "other.py").write_text("y = 1\n")
    first = f"*** Update File: {tmp_path}/app.py\n@@\n-x = 1\n+x = 2\n"
    patch = f"*** Begin Patch\n{first}{second.format(dir=tmp_path)}*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_multi_line_suppression_comment_into_code_asks(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("/*\neslint-disable no-console\n*/\nconsole.log(1)\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'notes.js'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_a_rust_attribute_out_of_a_python_comment_into_rust_asks(tmp_path: Path) -> None:
    source = tmp_path / "tool.py"
    source.write_text("#[allow(dead_code)]\nfn_f = 1\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'tool.rs'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_patch_header_with_surrounding_spaces_is_still_read(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    patch = f"*** Begin Patch\n  *** Update File: {target}  \n@@\n-x = 1\n+x = 1  # noqa\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_move_that_drops_a_markers_line_on_the_way_passes(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("x = 1  # noqa\n")
    patch = (
        f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'notes.py'}\n"
        "@@\n-x = 1  # noqa\n+x = 1\n*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "allow"


def test_an_inexact_hunk_that_adds_the_word_inside_a_quote_asks(tmp_path: Path) -> None:
    """Out of context the line reads as a string, but a loosely matched hunk may land inside a block comment."""
    target = tmp_path / "app.ts"
    target.write_text("/*\nnote\n*/\nfoo()\n")
    patch = f'*** Begin Patch\n*** Update File: {target}\n@@\n-note  \n+"ast-grep-ignore: rule"\n*** End Patch'
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_context_line_that_starts_with_stars_does_not_end_the_section(tmp_path: Path) -> None:
    """The applier ends a section only at a line that itself starts with `***`; a context line starts with a space."""
    target = tmp_path / "app.py"
    target.write_text('"""\n*** Notes\n"""\nx = 1\n')
    patch = (
        f'*** Begin Patch\n*** Update File: {target}\n@@\n """\n *** Notes\n """\n-x = 1\n+x = 1  # noqa\n'
        "*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_a_hunk_that_cannot_be_placed_counts_a_marker_its_lines_read_as_a_string(tmp_path: Path) -> None:
    """Parsed alone the lines are one string; placed, their first quotes close one, so the marker is a comment."""
    target = tmp_path / "app.py"
    target.write_text('a = """\ndoc\n"""\nb = """\ndoc\n"""\n')
    patch = f'*** Begin Patch\n*** Update File: {target}\n@@\n-doc\n+"""  # noqa: E501\n+x = """\n*** End Patch'
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_moving_code_into_a_document_that_mentions_a_marker_passes(tmp_path: Path) -> None:
    """After the move only the document exists, so only its own suffix decides what counts."""
    source = tmp_path / "app.py"
    source.write_text("x = 1\n")
    patch = (
        f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'notes.md'}\n"
        "@@\n x = 1\n+Write # noqa only with a reason.\n*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "allow"
