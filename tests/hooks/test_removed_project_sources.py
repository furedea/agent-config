"""A removed language project ignores sources that git ignores."""

import json
from pathlib import Path
import subprocess

import pytest

from tests.runtime import REPO_ROOT, load_script_module

selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")


def rules_for(root: Path) -> dict:
    path = root / ".agents/hooks/rules/related_test_extensions.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({}))
    return selection.load_defaults(REPO_ROOT / "agents/hooks/rules/related_test_defaults.json")


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


def touch(root: Path, name: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_git_ignored_sources_do_not_keep_a_removed_project_alive(tmp_path: Path) -> None:
    rules = rules_for(tmp_path)
    git(tmp_path, "init", "-q")
    touch(tmp_path, "scratch-workspace/app.js")
    (tmp_path / ".gitignore").write_text("*-workspace/\n")
    commands, errors = selection.language_plan(tmp_path, rules, ("package.json",))
    assert not errors
    assert commands == []


@pytest.mark.parametrize("tracked", [True, False])
def test_unignored_sources_keep_a_removed_project_reported(tmp_path: Path, tracked: bool) -> None:
    rules = rules_for(tmp_path)
    git(tmp_path, "init", "-q")
    touch(tmp_path, "src/app.js")
    if tracked:
        git(tmp_path, "add", "src/app.js")
    commands, errors = selection.language_plan(tmp_path, rules, ("package.json",))
    assert not commands
    assert errors and "package.json" in errors[0]


def test_deleted_tracked_sources_do_not_keep_a_removed_project_alive(tmp_path: Path) -> None:
    rules = rules_for(tmp_path)
    git(tmp_path, "init", "-q")
    touch(tmp_path, "src/app.js")
    git(tmp_path, "add", "src/app.js")
    (tmp_path / "src/app.js").unlink()
    commands, errors = selection.language_plan(tmp_path, rules, ("package.json", "src/app.js"))
    assert not errors
    assert commands == []


def test_outside_git_every_remaining_source_counts(tmp_path: Path) -> None:
    rules = rules_for(tmp_path)
    touch(tmp_path, "scratch-workspace/app.js")
    commands, errors = selection.language_plan(tmp_path, rules, ("package.json",))
    assert not commands
    assert errors and "package.json" in errors[0]


def test_outside_git_excluded_directories_do_not_count(tmp_path: Path) -> None:
    rules = rules_for(tmp_path)
    touch(tmp_path, "node_modules/dep/index.js")
    commands, errors = selection.language_plan(tmp_path, rules, ("package.json",))
    assert not errors
    assert commands == []
