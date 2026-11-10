"""Go verification runs `go test` for the packages that contain changed files."""

import json
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT, load_script_module

selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")


def project(tmp_path: Path, mappings: dict) -> dict:
    path = tmp_path / ".agents/hooks/rules/related_test_extensions.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(mappings))
    return selection.load_defaults(REPO_ROOT / "agents/hooks/rules/related_test_defaults.json")


def touch_all(root: Path, names: list[str]) -> None:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def go_project(tmp_path: Path, files: list[str]) -> dict:
    rules = project(tmp_path, {})
    touch_all(tmp_path, ["go.mod", *files])
    return rules


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (("pkg/parser/parser.go",), [("go", "test", "./pkg/parser")]),
        (("pkg/parser/parser_test.go",), [("go", "test", "./pkg/parser")]),
        (("main.go",), [("go", "test", ".")]),
        (
            ("cmd/app/main.go", "internal/util/util.go", "internal/util/more.go"),
            [("go", "test", "./cmd/app", "./internal/util")],
        ),
    ],
)
def test_go_sources_select_the_packages_that_contain_them(
    tmp_path: Path, changed: tuple[str, ...], expected: list[tuple[str, ...]]
) -> None:
    rules = go_project(tmp_path, list(changed))
    commands, errors = selection.language_plan(tmp_path, rules, changed)
    assert not errors
    assert [item.arguments for item in commands] == expected
    assert [item.label for item in commands] == ["go"]


@pytest.mark.parametrize("changed", ["go.mod", "go.sum", "go.work", "go.work.sum"])
def test_go_configuration_changes_select_the_full_suite(tmp_path: Path, changed: str) -> None:
    rules = go_project(tmp_path, [changed, "pkg/a/a.go"])
    commands, errors = selection.language_plan(tmp_path, rules, (changed,))
    assert not errors
    assert [item.arguments for item in commands] == [("go", "test", "./...")]


def test_go_sources_without_a_module_marker_report_instead_of_passing(tmp_path: Path) -> None:
    rules = project(tmp_path, {})
    touch_all(tmp_path, ["pkg/a/a.go"])
    commands, errors = selection.language_plan(tmp_path, rules, ("pkg/a/a.go",))
    assert not commands
    assert errors and "go.mod" in errors[0]


def test_go_sources_outside_a_resolvable_package_fall_back_to_the_full_suite(tmp_path: Path) -> None:
    rules = go_project(tmp_path, [])
    commands, errors = selection.language_plan(tmp_path, rules, ("pkg/deleted/old.go",))
    assert not errors
    assert [item.arguments for item in commands] == [("go", "test", "./...")]


def test_go_package_names_cannot_become_options(tmp_path: Path) -> None:
    rules = go_project(tmp_path, ["-race/a.go"])
    commands, _ = selection.language_plan(tmp_path, rules, ("-race/a.go",))
    assert [item.arguments for item in commands] == [("go", "test", "./-race")]


def test_removing_a_whole_go_project_skips_its_verification(tmp_path: Path) -> None:
    rules = project(tmp_path, {})
    commands, errors = selection.language_plan(tmp_path, rules, ("go.mod", "go.sum", "main.go"))
    assert not errors
    assert commands == []


def test_deleting_the_last_go_file_of_a_package_selects_the_full_suite(tmp_path: Path) -> None:
    rules = go_project(tmp_path, ["pkg/old/README.md", "pkg/live/live.go"])
    commands, errors = selection.language_plan(tmp_path, rules, ("pkg/old/old.go",))
    assert not errors
    assert [item.arguments for item in commands] == [("go", "test", "./...")]


def test_a_package_that_keeps_other_go_files_is_still_selected(tmp_path: Path) -> None:
    rules = go_project(tmp_path, ["pkg/live/live.go"])
    commands, errors = selection.language_plan(tmp_path, rules, ("pkg/live/gone.go",))
    assert not errors
    assert [item.arguments for item in commands] == [("go", "test", "./pkg/live")]


def test_nested_go_files_do_not_make_their_parent_directory_a_package(tmp_path: Path) -> None:
    rules = go_project(tmp_path, ["pkg/deep/inner/inner.go"])
    commands, _ = selection.language_plan(tmp_path, rules, ("pkg/deep/old.go",))
    assert [item.arguments for item in commands] == [("go", "test", "./...")]
