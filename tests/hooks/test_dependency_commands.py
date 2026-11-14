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
        "uv add --dev pytest",
        "uv add pytest --dev",
    ],
)
def test_global_installs_and_the_legacy_dev_group_are_denied_wherever_the_flag_sits(
    git_project: Path, command: str
) -> None:
    assert judged(git_project, command, "forbidden") == "deny"
