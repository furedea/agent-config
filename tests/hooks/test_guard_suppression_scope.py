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


def test_without_the_scanner_turning_a_go_string_into_a_nolint_comment_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")
    target = tmp_path / "user.go"
    target.write_text('package a\n\nfunc f() {\n\ts := "//nolint"\n\t_ = s\n}\n')
    edits = [
        {"old_string": 's := "//nolint"', "new_string": "//nolint"},
        {"old_string": "\t_ = s\n", "new_string": ""},
    ]
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_without_the_scanner_an_edit_away_from_an_unchanged_suppression_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")
    target = tmp_path / "a.py"
    target.write_text("import os  # noqa: F401\nx = 1\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "x = 1", "new_string": "x = 2"}) == "allow"


def test_turning_a_rust_attribute_inside_a_raw_string_into_code_asks(tmp_path: Path) -> None:
    target = tmp_path / "lib.rs"
    target.write_text('const S: &str = r#"\n#[allow(dead_code)]\n"#;\nfn f() {}\n')
    edits = [
        {"old_string": 'const S: &str = r#"\n', "new_string": ""},
        {"old_string": '\n"#;\n', "new_string": "\n"},
    ]
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_editing_code_beside_an_unchanged_rust_attribute_passes(tmp_path: Path) -> None:
    target = tmp_path / "lib.rs"
    target.write_text("#[allow(dead_code)]\nfn f() {}\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "fn f()", "new_string": "fn g()"}) == "allow"


def test_without_the_scanner_removing_string_delimiters_around_a_marker_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a parser the guard cannot see a multi-line string end, so changing a delimiter line near one asks."""
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")
    target = tmp_path / "app.ts"
    target.write_text("const text = `\n// @ts-ignore\n`;\nfoo(1);\n")
    edits = [{"old_string": "const text = `\n", "new_string": ""}, {"old_string": "\n`;\n", "new_string": "\n"}]
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_a_new_rust_attribute_inside_a_macro_body_asks(tmp_path: Path) -> None:
    target = tmp_path / "lib.rs"
    target.write_text("macro_rules! m {\n    () => {\n        fn f() {}\n    };\n}\n")
    values = {
        "file_path": str(target),
        "old_string": "        fn f()",
        "new_string": "        #[allow(dead_code)]\n        fn f()",
    }
    assert decide("Edit", values) == "ask"


def test_a_suppression_in_a_file_with_an_upper_case_suffix_asks() -> None:
    values = {"file_path": "src/App.PY", "old_string": "x = 1", "new_string": "x = 1  # noqa"}
    assert decide("Edit", values) == "ask"


def test_an_ast_grep_marker_glued_to_a_word_asks() -> None:
    values = {"file_path": "src/app.py", "old_string": "x = 1", "new_string": "x = 1  # xast-grep-ignore"}
    assert decide("Edit", values) == "ask"


def test_without_the_scanner_a_changed_html_comment_end_near_a_marker_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard.comment_nodes, "SCANNER", "ast-grep-missing-for-test")
    target = tmp_path / "app.js"
    target.write_text("a\n// @ts-ignore\nfoo()\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "a\n", "new_string": "--!> x\n"}) == "ask"


def test_a_first_line_string_that_holds_the_word_is_no_file_suppression(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1\n")
    content = 'MARKER = "ast-grep-ignore"\n\nx = 1\n'
    assert decide("Write", {"file_path": str(target), "content": content}) == "allow"


def test_a_relative_path_is_read_in_the_payloads_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Read elsewhere, the file looks empty and the edit's fragments hold no marker, so nothing would ask."""
    work, elsewhere = tmp_path / "work", tmp_path / "elsewhere"
    work.mkdir()
    elsewhere.mkdir()
    (work / "app.py").write_text('s = """\n# noqa\n"""\n')
    monkeypatch.chdir(elsewhere)
    edits = [{"old_string": 's = """\n', "new_string": ""}, {"old_string": '\n"""\n', "new_string": "\n"}]
    payload = {"tool_name": "MultiEdit", "cwd": str(work), "tool_input": {"file_path": "app.py", "edits": edits}}
    assert guard.decide(payload).decision == "ask"
