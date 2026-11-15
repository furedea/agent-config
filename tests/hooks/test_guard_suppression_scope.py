"""A suppression cannot reach the user's review by another route: a move, a wider scope, or another tool's fields."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression_for_scope")


def decide(tool: str, values: dict) -> str:
    return guard.decide({"tool_name": tool, "tool_input": values}).decision


@pytest.mark.parametrize("text", ["//nolint", "//nolint:errcheck // closing a read-only file", "// nolint:all"])
def test_a_new_go_nolint_asks(text: str) -> None:
    values = {"file_path": "pkg/store/user.go", "old_string": "f()", "new_string": f"f() {text}"}
    assert decide("Edit", values) == "ask"


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


@pytest.mark.parametrize(
    "before,old,new",
    [
        (
            "# ast-grep-ignore: rule_a\nbad()\n",
            "# ast-grep-ignore: rule_a\nbad()",
            "# ast-grep-ignore: rule_a\n\nbad()",
        ),
        ("# ast-grep-ignore: rule_a\nx = 1\n\nbad()\n", "x = 1\n", ""),
    ],
    ids=["blank line added", "line removed"],
)
def test_an_edit_that_turns_a_line_marker_into_a_file_marker_asks(
    tmp_path: Path, before: str, old: str, new: str
) -> None:
    target = tmp_path / "app.py"
    target.write_text(before)
    assert decide("Edit", {"file_path": str(target), "old_string": old, "new_string": new}) == "ask"


def test_an_edit_below_an_unchanged_file_marker_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\n\nx = 1\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "x = 1", "new_string": "x = 2"}) == "allow"


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
    "values",
    [
        {"path": "src/app.py", "command": "str_replace", "old_str": "x = 1", "new_str": "x = 1  # noqa"},
        {"path": "src/app.py", "command": "create", "file_text": "x = 1  # noqa\n"},
    ],
    ids=["str_replace", "create"],
)
def test_editor_tool_fields_are_inspected(values: dict) -> None:
    assert decide("Edit", values) == "ask"


@pytest.mark.parametrize(
    "hunk", ["@@\n+\n bad()", "@@ bad()\n+\n bad()"], ids=["context on the second line", "anchor on the second line"]
)
def test_a_patch_hunk_anchored_below_a_top_marker_asks(tmp_path: Path, hunk: str) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nbad()\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n{hunk}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_an_editor_insert_of_a_blank_line_after_a_top_marker_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nbad()\n")
    values = {"path": str(target), "command": "insert", "insert_line": 1, "new_str": ""}
    assert decide("Edit", values) == "ask"


def test_lines_are_split_as_the_scanner_splits_them(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\u2028# ast-grep-ignore: rule_a\nbad()\n")
    values = {"file_path": str(target), "old_string": "\nbad()", "new_string": "\n\nbad()"}
    assert decide("Edit", values) == "ask"


def test_a_patch_that_removes_the_lines_above_a_marker_asks(tmp_path: Path) -> None:
    """Deleting the first line can move a marker followed by a blank line to the top, where it covers the file."""
    target = tmp_path / "app.py"
    target.write_text("x = 1\n# ast-grep-ignore: rule_a\n\nbad()\n")
    patch = f"*** Begin Patch\n*** Update File: {target}\n@@\n-x = 1\n # ast-grep-ignore: rule_a\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_an_edit_that_does_not_apply_to_a_file_with_a_marker_asks(tmp_path: Path) -> None:
    """When the guard cannot rebuild the file it cannot see the marker's scope, so it fails closed."""
    target = tmp_path / "app.py"
    target.write_text("x = 1\n# ast-grep-ignore: rule_a\n\nbad()\n")
    values = {"file_path": str(target), "old_string": "x  =  1\n", "new_string": ""}
    assert decide("Edit", values) == "ask"


def test_an_edit_that_does_not_apply_to_a_file_without_a_marker_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\nbad()\n")
    values = {"file_path": str(target), "old_string": "x  =  1\n", "new_string": ""}
    assert decide("Edit", values) == "allow"


def test_turning_a_marker_inside_a_string_into_a_comment_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("value = 'ast-grep-ignore'\nbad()\n")
    values = {"file_path": str(target), "old_string": "value = '", "new_string": "# "}
    assert decide("Edit", values) == "ask"


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


def test_a_string_that_holds_a_whole_marker_turned_into_a_comment_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text('s = "# ast-grep-ignore"\nbad()\n')
    values = {"file_path": str(target), "old_string": 's = "', "new_string": ""}
    assert decide("Edit", values) == "ask"


def test_editing_code_with_an_escaped_quote_beside_an_unchanged_marker_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text('x = "a\\"b"  # ast-grep-ignore: rule_a\n')
    assert decide("Edit", {"file_path": str(target), "old_string": "x =", "new_string": "y ="}) == "allow"


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


@pytest.mark.parametrize(
    "name,before,edits",
    [
        (
            "app.ts",
            'const marker =\n  "ast-grep-ignore: rule";\nfoo()\n',
            [
                {"old_string": "const marker =\n", "new_string": "/*\n"},
                {"old_string": ";\nfoo", "new_string": ";\n*/\nfoo"},
            ],
        ),
        (
            "app.py",
            'DOC = """\n# ast-grep-ignore: rule\n"""\nbad()\n',
            [{"old_string": 'DOC = """\n', "new_string": ""}, {"old_string": '\n"""\n', "new_string": "\n"}],
        ),
    ],
    ids=["into a block comment", "out of a multi-line string"],
)
def test_an_edit_that_puts_a_marker_line_into_a_comment_across_lines_asks(
    tmp_path: Path, name: str, before: str, edits: list[dict]
) -> None:
    target = tmp_path / name
    target.write_text(before)
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_editing_code_beside_an_unchanged_marker_in_a_block_comment_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.ts"
    target.write_text("/*\n  ast-grep-ignore: rule\n*/\nfoo()\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "foo()", "new_string": "bar()"}) == "allow"


def test_an_edit_that_ends_a_heredoc_before_a_marker_line_asks(tmp_path: Path) -> None:
    target = tmp_path / "run.sh"
    target.write_text("cat <<EOF\n# ast-grep-ignore: rule\nEOF\nbad\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "cat <<EOF\n", "new_string": ""}) == "ask"


def test_moving_a_marker_out_of_a_heredoc_into_python_asks(tmp_path: Path) -> None:
    source = tmp_path / "run.sh"
    source.write_text("cat <<EOF\n# ast-grep-ignore: rule\nEOF\n")
    patch = f"*** Begin Patch\n*** Update File: {source}\n*** Move to: {tmp_path / 'run.py'}\n*** End Patch"
    assert decide("apply_patch", {"input": patch}) == "ask"


@pytest.mark.parametrize(
    "name,before,edits",
    [
        ("ci.yml", "key: |\n  # ast-grep-ignore: rule\nx: 1\n", [{"old_string": "key: |\n  ", "new_string": ""}]),
        (
            "lib.rs",
            'const S: &str = r#"foo "\n// ast-grep-ignore: rule\n"#;\nfn f() {}\n',
            [
                {"old_string": 'const S: &str = r#"foo "\n', "new_string": ""},
                {"old_string": '\n"#;\n', "new_string": "\n"},
            ],
        ),
    ],
    ids=["out of a YAML block scalar", "out of a Rust raw string"],
)
def test_an_edit_that_turns_a_string_line_into_a_marker_comment_asks(
    tmp_path: Path, name: str, before: str, edits: list[dict]
) -> None:
    target = tmp_path / name
    target.write_text(before)
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_without_the_scanner_any_change_to_a_file_with_a_marker_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ast-grep the guard cannot tell comments from strings, so it fails closed."""
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")
    target = tmp_path / "app.py"
    target.write_text("x = 1  # ast-grep-ignore: rule_a\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "x = 1", "new_string": "y = 2"}) == "ask"


def test_turning_a_go_string_into_a_nolint_comment_asks(tmp_path: Path) -> None:
    target = tmp_path / "user.go"
    target.write_text('package a\n\nfunc f() {\n\ts := "//nolint"\n\t_ = s\n}\n')
    edits = [
        {"old_string": 's := "//nolint"', "new_string": "//nolint"},
        {"old_string": "\t_ = s\n", "new_string": ""},
    ]
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_editing_code_beside_an_unchanged_nolint_comment_passes(tmp_path: Path) -> None:
    target = tmp_path / "user.go"
    target.write_text("package a\n\nfunc f() {\n\tg() //nolint:errcheck // closing a read-only file\n}\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "\tg()", "new_string": "\th()"}) == "allow"


@pytest.mark.parametrize(
    "name,before,after",
    [
        ("app.py", 'value: int = "# type: ignore"\n', 'value: int = "# type: ignore"  # type: ignore\n'),
        ("app.py", 'print("# noqa")\n', 'print("# noqa")  # noqa\n'),
        (
            "app.ts",
            "foo(); // eslint-disable-line no-console\n",
            "/* eslint-disable */ foo(); // eslint-disable-line no-console\n",
        ),
    ],
    ids=["type ignore after a string", "noqa after a string", "second directive on the line"],
)
def test_a_second_suppression_on_the_same_line_asks(tmp_path: Path, name: str, before: str, after: str) -> None:
    target = tmp_path / name
    target.write_text(before)
    values = {"file_path": str(target), "old_string": before.rstrip("\n"), "new_string": after.rstrip("\n")}
    assert decide("Edit", values) == "ask"


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
