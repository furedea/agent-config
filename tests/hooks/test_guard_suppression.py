"""Adding a lint or type-check suppression to code is the user's call, never an agent's shortcut."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_suppression.py", "guard_suppression")


def decide(tool: str, values: dict) -> str:
    return guard.decide({"tool_name": tool, "tool_input": values}).decision


@pytest.mark.parametrize(
    "path,text",
    [
        ("src/app.py", "def f(a, b, c, d):  # noqa: PLR0913 -- wraps a fixed C API"),
        ("src/app.py", "value = cast(x)  # type: ignore[arg-type]"),
        ("src/app.ts", "// oxlint-disable-next-line max-params -- mirrors the DOM API"),
        ("src/app.ts", "// @ts-expect-error -- third-party types are wrong"),
        ("src/lib.rs", '#[expect(clippy::too_many_arguments, reason = "FFI signature")]'),
        ("src/lib.rs", "#![allow(clippy::pedantic)]"),
    ],
)
def test_a_new_suppression_in_code_asks(path: str, text: str) -> None:
    assert decide("Edit", {"file_path": path, "old_string": "x = 1", "new_string": f"x = 1\n{text}"}) == "ask"


@pytest.mark.parametrize(
    "path,text",
    [
        ("src/app.py", "# ast-grep-ignore"),
        ("src/app.py", "# ast-grep-ignore: py_no_staticmethod"),
        ("src/app.py", "value = helper()  # ast-grep-ignore: py_no_unittest, py_no_unittest_mock"),
        ("scripts/run.sh", "# ast-grep-ignore: bash_local_underscore_prefix"),
        ("src/app.ts", "// ast-grep-ignore: ts_no_namespace_import"),
        ("src/app.tsx", "{/* ast-grep-ignore */}"),
        ("src/lib.rs", "// ast-grep-ignore"),
        ("pkg/store/user.go", "// ast-grep-ignore: go_error_no_string_matching"),
        ("src/lib.rs", "/// ast-grep-ignore"),
        ("src/app.ts", "/* ast-grep-ignore: ts_no_namespace_import */"),
        (".github/workflows/ci.yml", "# ast-grep-ignore: project_rule"),
        ("config/app.yaml", "  # ast-grep-ignore"),
        ("modules/home.nix", "# ast-grep-ignore: project_rule"),
        ("src/app.py", "print(1)  # Do not add ast-grep-ignore here"),
        ("src/app.py", "# note: ast-grep-ignore: py_no_staticmethod"),
    ],
)
def test_a_new_ast_grep_suppression_asks(path: str, text: str) -> None:
    verdict = guard.decide(
        {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "x", "new_string": f"x\n{text}"}}
    )
    assert verdict.decision == "ask"
    assert "ast-grep-ignore" in verdict.reason


@pytest.mark.parametrize(
    "old,new",
    [
        ("# ast-grep-ignore: rule_a\nx = 1", "# ast-grep-ignore\nx = 1"),
        ("x = 1  # ast-grep-ignore: rule_a", "x = 1  # ast-grep-ignore: rule_a, rule_b"),
    ],
    ids=["narrow to bare", "one more rule"],
)
def test_widening_an_ast_grep_suppression_asks(old: str, new: str) -> None:
    assert decide("Edit", {"file_path": "src/app.py", "old_string": old, "new_string": new}) == "ask"


def test_editing_code_beside_an_unchanged_ast_grep_suppression_passes() -> None:
    values = {
        "file_path": "src/app.py",
        "old_string": "x = 1  # ast-grep-ignore: r",
        "new_string": "y = 2  # ast-grep-ignore: r",
    }
    assert decide("Edit", values) == "allow"


@pytest.mark.parametrize("tool", ["Edit", "MultiEdit"])
def test_widening_a_suppression_by_editing_part_of_its_line_asks(tmp_path: Path, tool: str) -> None:
    target = tmp_path / "app.py"
    target.write_text("# ast-grep-ignore: rule_a\nx = 1\n")
    edit = {"old_string": ": rule_a", "new_string": ""}
    values = {"file_path": str(target), **edit} if tool == "Edit" else {"file_path": str(target), "edits": [edit]}
    assert decide(tool, values) == "ask"


def test_a_later_multiedit_step_that_widens_a_suppression_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("a: rule_a\n# ast-grep-ignore: rule_a\nx = 1\n")
    edits = [{"old_string": "a: rule_a", "new_string": "a = 1"}, {"old_string": ": rule_a", "new_string": ""}]
    assert decide("MultiEdit", {"file_path": str(target), "edits": edits}) == "ask"


def test_a_replace_all_that_widens_a_later_suppression_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("a: rule_a\n# ast-grep-ignore: rule_a\nx = 1\n")
    values = {"file_path": str(target), "old_string": ": rule_a", "new_string": "", "replace_all": True}
    assert decide("Edit", values) == "ask"


def test_editing_part_of_a_line_beside_an_unchanged_suppression_passes(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("x = 1  # ast-grep-ignore: rule_a\n")
    assert decide("Edit", {"file_path": str(target), "old_string": "x = 1", "new_string": "y = 2"}) == "allow"


def test_ast_grep_ignore_in_a_prose_file_passes() -> None:
    text = "Use `// ast-grep-ignore: <rule>` only with approval."
    assert decide("Edit", {"file_path": "docs/lint.md", "old_string": "x", "new_string": f"x\n{text}"}) == "allow"


RULE_LANGUAGE_SUFFIXES = {
    "python": ".py",
    "go": ".go",
    "rust": ".rs",
    "typescript": ".ts",
    "tsx": ".tsx",
    "javascript": ".js",
    "bash": ".sh",
    "yaml": ".yml",
}


def test_every_static_rule_language_is_inspected_for_suppressions() -> None:
    rules = Path(__file__).resolve().parents[2] / "agents/hooks/lint/rules"
    languages = {
        line.removeprefix("language:").strip()
        for rule in rules.rglob("*.yml")
        for line in rule.read_text().splitlines()
        if line.startswith("language:")
    }
    assert languages <= RULE_LANGUAGE_SUFFIXES.keys(), "map the new rule language to its file suffix"
    assert {RULE_LANGUAGE_SUFFIXES[language] for language in languages} <= guard.MARKER_SUFFIXES["ast-grep-ignore"]


def test_a_write_that_adds_a_suppression_asks(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("import os  # noqa: F401\n")
    content = "import os  # noqa: F401\nimport sys  # noqa: F401\n"
    assert decide("Write", {"file_path": str(target), "content": content}) == "ask"


@pytest.mark.parametrize(
    "tool,values",
    [
        (
            "Edit",
            {"file_path": "src/app.py", "old_string": "a = 1  # noqa: E501", "new_string": "b = 1  # noqa: E501"},
        ),
        ("Edit", {"file_path": "src/app.py", "old_string": "a = 1  # noqa: E501", "new_string": "a = 1"}),
        ("Edit", {"file_path": "docs/lint.md", "old_string": "x", "new_string": "Use `# noqa: E501` sparingly."}),
        ("Edit", {"file_path": "src/app.py", "old_string": "x = 1", "new_string": "x = 2"}),
    ],
    ids=["moved, not added", "removed", "prose, not code", "no suppression"],
)
def test_edits_that_do_not_add_a_suppression_pass(tool: str, values: dict) -> None:
    assert decide(tool, values) == "allow"


def test_an_apply_patch_that_adds_a_suppression_asks() -> None:
    patch = (
        "*** Begin Patch\n*** Update File: src/app.py\n@@\n-def f(a, b, c, d):\n"
        "+def f(a, b, c, d):  # noqa: PLR0913 -- legacy\n*** End Patch"
    )
    assert decide("apply_patch", {"input": patch}) == "ask"


def test_the_reason_names_the_file_and_the_suppression() -> None:
    verdict = guard.decide(
        {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py", "old_string": "", "new_string": "x  # noqa"}}
    )
    assert "src/app.py" in verdict.reason
    assert "noqa" in verdict.reason
