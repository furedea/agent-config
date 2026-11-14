"""Dependency changes run inside the project; global installs and the legacy dev group stay denied."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")


def judged(project: Path, command: str, kind: str) -> str:
    payload = {"cwd": str(project), "session_id": "s", "tool_name": "Bash", "tool_input": {"command": command}}
    return guard.decide(kind, payload).decision


@pytest.mark.parametrize(
    "command",
    [
        "uv add httpx",
        "uv add --group audit vulture",
        "uv lock --upgrade-package ruff",
        "cargo add serde --features derive",
        "cargo update -p serde",
        "go get example.com/module@v1.2.3",
        "go mod tidy",
        "pnpm add zod",
        "pnpm add -D vitest",
        "nix flake update nixpkgs",
    ],
)
def test_dependency_changes_inside_the_project_run(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "forbidden") == "allow"
    assert judged(git_project, command, "allowed") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "pnpm add -g cowsay",
        "pnpm add cowsay -g",
        "pnpm add cowsay --global",
        "pnpm add -Dg cowsay",
        "pnpm add cowsay --global-dir /tmp/g",
        "pnpm add cowsay --global-dir=/tmp/g",
        "pnpm add cowsay --glob",
        "pnpm add cowsay --global=true",
        "pnpm add cowsay --config.global=true",
        "pnpm add cowsay --config.global-dir=/tmp/g",
        "pnpm --global add cowsay",
        "uv add --dev pytest",
        "uv add pytest --dev",
    ],
)
def test_global_installs_and_the_legacy_dev_group_are_denied_wherever_the_flag_sits(
    git_project: Path, command: str
) -> None:
    assert judged(git_project, command, "forbidden") == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "npm_config_global=true pnpm add cowsay",
        "env npm_config_global=true pnpm add cowsay",
        "PNPM_HOME=/tmp/g pnpm add cowsay",
        "export npm_config_global=true && pnpm add cowsay",
        "declare -x npm_config_global=true; pnpm add cowsay",
        "source settings.sh && pnpm add cowsay",
        "npm_config_dev=true uv add pytest",
        "UV_PROJECT_ENVIRONMENT=/tmp/env uv add httpx",
    ],
)
def test_a_dependency_change_beside_settings_the_guard_cannot_read_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "ask"


@pytest.mark.parametrize("command", ["pnpm add zod && pnpm test", "uv add httpx && uv run --frozen pytest"])
def test_a_dependency_change_beside_other_commands_runs(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "pnpm add zod --dir /other/repo",
        "pnpm -C /other/repo add zod",
        "pnpm add zod --prefix=/other",
        "uv add httpx --project /other/repo",
        "uv add httpx --directory=/other/repo",
        "uv add --script /other/tool.py httpx",
        "uv lock --upgrade --project /other/repo",
        "cargo add serde --manifest-path /other/Cargo.toml",
        "cargo update --manifest-path=/other/Cargo.toml",
        "go get -C /other/module example.com/x@v1.0.0",
        "go mod tidy -modfile=/other/go.mod",
        "nix flake update --flake /other/flake",
        "nix flake update --flake=/other/flake",
        "npm_config_global=true; export npm_config_global; pnpm add cowsay",
        "PNPM_HOME=/tmp/g; pnpm add cowsay",
    ],
)
def test_a_dependency_change_aimed_at_another_place_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "ask"
