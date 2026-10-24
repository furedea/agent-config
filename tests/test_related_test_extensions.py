"""Repository test mappings name existing sources and targets and reach tests that names alone miss."""

import fnmatch
import json
import subprocess

import pytest

from tests.runtime import REPO_ROOT, load_script_module

selection = load_script_module("agents/hooks/lib/check_selection.py", "check_selection")

RULES = REPO_ROOT / ".agents/hooks/rules/related_test_extensions.json"
DEFAULTS = REPO_ROOT / "agents/hooks/rules/related_test_defaults.json"


@pytest.fixture(scope="module")
def extension() -> dict[str, list[str]]:
    return json.loads(RULES.read_text())


@pytest.fixture(scope="module")
def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.splitlines()


def selected_tests(*changed: str) -> set[str]:
    commands, errors = selection.language_plan(REPO_ROOT, selection.load_defaults(DEFAULTS), changed)
    assert not errors
    return {argument for command in commands for argument in command.arguments if argument.startswith("tests/")}


def test_extension_values_are_nonempty_arrays_of_paths(extension: dict[str, list[str]]) -> None:
    assert extension
    for source, targets in extension.items():
        assert isinstance(targets, list) and targets, source
        assert all(isinstance(target, str) and target for target in targets), source


def test_every_extension_source_matches_a_repository_file(
    extension: dict[str, list[str]], repository_files: list[str]
) -> None:
    unmatched = {source for source in extension if not fnmatch.filter(repository_files, source)}
    assert not unmatched


def test_every_extension_target_exists(extension: dict[str, list[str]]) -> None:
    missing = {target for targets in extension.values() for target in targets if not (REPO_ROOT / target).is_file()}
    assert not missing


@pytest.mark.parametrize(
    ("source", "required"),
    [
        ("agents/hooks/lib/command_policy.py", "tests/test_command_permission_sync.py"),
        ("agents/command_permissions.json", "tests/test_command_permission_sync.py"),
        ("agents/hooks/rules/allowed_commands.json", "tests/hooks/test_allowed_command.py"),
        ("agents/hooks/rules/related_test_defaults.json", "tests/hooks/test_check_selection.py"),
        ("agents/claude/settings.json", "tests/claude/test_settings.py"),
        ("agents/codex/config.toml", "tests/codex/test_config.py"),
        ("agents/hooks.json", "tests/test_hook_generation.py"),
        ("agents/hooks/lib/provider_adapter.py", "tests/test_provider_adapters.py"),
        ("agents/codex/hooks/hook_adapter.py", "tests/codex/test_hook_adapter_cli.py"),
        ("agents/hooks/lib/herdr_grammar.py", "tests/hooks/test_herdr_ownership.py"),
        ("agents/skills/explain-visually/assets/template.html", "tests/skills/explain-visually/test_verify_page.py"),
        (".agents/hooks/rules/related_test_extensions.json", "tests/test_related_test_extensions.py"),
    ],
)
def test_changed_source_selects_tests_its_name_does_not_match(source: str, required: str) -> None:
    assert required in selected_tests(source)
