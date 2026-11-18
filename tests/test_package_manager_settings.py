"""User-level package-manager settings, which Nix pins, cannot be changed from an agent session.

They hold the release-age wait and the fetch source. The sandbox and the provider permissions stop
the change, so these routes stay closed without the command guard (#199, #219). Project files,
environment variables, and command-line options can still override the settings; those routes
are left to the guard and the dependency `ask` prefixes.
"""

import json
import tomllib
from pathlib import Path

import pytest

from tests.runtime import REPO_ROOT, CliRunner, load_script_module

PINNED_DIRECTORIES = (
    "~/.config/uv",
    "~/.config/pnpm",
    "~/Library/Preferences/pnpm",
    "~/.config/nix",
)
PINNED_FILES = (
    "~/.npmrc",
    "~/.cargo/config.toml",
    "~/.cargo/config",
    "~/Library/Application Support/go/env",
)
PINNED_PATHS = PINNED_DIRECTORIES + PINNED_FILES
EDITED_FILES = (
    "~/.config/uv/uv.toml",
    "~/.config/pnpm/rc",
    "~/Library/Preferences/pnpm/rc",
    "~/.config/nix/nix.conf",
    *PINNED_FILES,
)

policy = load_script_module("agents/hooks/lib/secret_path_policy.py", "secret_path_policy")
RULES = policy.load(REPO_ROOT / "agents/hooks/rules/secret_path_policy.json")


@pytest.fixture(scope="module")
def claude_settings(agent_harness: CliRunner, tmp_path_factory: pytest.TempPathFactory) -> dict:
    path = tmp_path_factory.mktemp("claude-settings") / "settings.json"
    agent_harness("generate-claude-settings", "--output", str(path))
    return json.loads(path.read_text())


@pytest.mark.integration
@pytest.mark.parametrize("path", PINNED_PATHS)
def test_claude_shell_commands_cannot_write_pinned_package_manager_settings(claude_settings: dict, path: str) -> None:
    assert path in claude_settings["sandbox"]["filesystem"]["denyWrite"]


@pytest.mark.integration
@pytest.mark.parametrize("path", EDITED_FILES)
def test_claude_file_tools_cannot_edit_pinned_package_manager_settings(claude_settings: dict, path: str) -> None:
    patterns = [rule[5:-1] for rule in claude_settings["permissions"]["deny"] if rule.startswith("Edit(")]
    assert any(Path(path).full_match(pattern) for pattern in patterns), path


@pytest.mark.integration
@pytest.mark.parametrize("path", PINNED_PATHS)
def test_codex_commands_cannot_write_pinned_package_manager_settings_even_from_a_home_workspace(
    agent_harness: CliRunner, tmp_path: Path, path: str
) -> None:
    config_path = tmp_path / "config.toml"
    agent_harness("generate-codex-config-source", "--output", str(config_path))
    filesystem = tomllib.loads(config_path.read_text())["permissions"]["guarded"]["filesystem"]
    assert filesystem[path] == "read"


@pytest.mark.parametrize("path", EDITED_FILES)
def test_provider_file_edits_of_pinned_package_manager_settings_are_blocked(path: str) -> None:
    assert policy.blocked_rule(path, RULES, editing=True) is not None


@pytest.mark.parametrize("path", EDITED_FILES)
def test_commands_may_still_read_pinned_package_manager_settings(path: str) -> None:
    assert policy.blocked_rule(path, RULES) is None
