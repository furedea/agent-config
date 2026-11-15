"""uv dependency changes run inside the age limit; anything that could escape it or the project asks."""

import json
from pathlib import Path

import pytest
from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
POLICY = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]


def judged(project: Path, command: str, kind: str) -> str:
    payload = {"cwd": str(project), "session_id": "s", "tool_name": "Bash", "tool_input": {"command": command}}
    return guard.decide(kind, payload).decision


def decisions(prefix: tuple[str, ...]) -> set[str]:
    return {rule["decision"] for rule in POLICY if tuple(rule["prefix"]) == prefix}


@pytest.mark.parametrize(
    "command",
    [
        "uv add httpx",
        "uv add httpx==0.27.0",
        'uv add "httpx>=0.27"',
        "uv add --group audit vulture",
        "uv lock --upgrade-package ruff",
        "uv lock --upgrade-package ruff==0.5.0",
        "uv add httpx && uv run --frozen pytest",
        "git status && uv add httpx",
    ],
)
def test_uv_dependency_changes_inside_the_age_limit_run(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "forbidden") == "allow"
    assert judged(git_project, command, "allowed") == "allow"


@pytest.mark.parametrize(
    "prefix",
    [
        ("pnpm", "add"),
        ("cargo", "add"),
        ("cargo", "update"),
        ("go", "get"),
        ("go", "mod", "tidy"),
        ("nix", "flake", "update"),
    ],
)
def test_dependency_changes_no_age_limit_guards_ask(prefix: tuple[str, ...]) -> None:
    assert decisions(prefix) == {"ask"}


@pytest.mark.parametrize(
    "command",
    [
        "uv add httpx --exclude-newer 2099-01-01",
        "uv add httpx --exclude-newer=2099-01-01",
        "uv add httpx --exclude-newer-package httpx=2099-01-01",
        "uv lock --upgrade --no-config",
        "uv add httpx --project /other/repo",
        "uv add httpx --directory=/other/repo",
        "uv add --script /other/tool.py httpx",
        "uv lock --upgrade --config-file /other/uv.toml",
        "UV_EXCLUDE_NEWER=2099-01-01 uv add httpx",
        "env UV_NO_CONFIG=1 uv add httpx",
        "export UV_EXCLUDE_NEWER=2099-01-01 && uv add httpx",
        "UV_EXCLUDE_NEWER=2099-01-01; export UV_EXCLUDE_NEWER; uv add httpx",
        "set -a; UV_NO_CONFIG=1; uv add httpx",
        "source settings.sh && uv add httpx",
        "cd /other/repo && uv add httpx",
        "(cd ../sibling; uv add httpx)",
        "pushd /x && uv lock --upgrade",
        "python3 write_settings.py && uv add httpx",
        "nohup uv add httpx",
    ],
)
def test_a_uv_change_that_could_escape_the_limit_or_the_project_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "ask"


@pytest.mark.parametrize("name", ["pyproject.toml", "uv.toml"])
def test_a_project_that_sets_its_own_age_limit_asks(git_project: Path, name: str) -> None:
    (git_project / name).write_text('[tool.uv]\nexclude-newer = "2099-01-01T00:00:00Z"\n')
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "pnpm add -g cowsay",
        "pnpm add cowsay -g",
        "pnpm add cowsay -g=true",
        "pnpm add cowsay --global",
        "pnpm add cowsay --glob",
        "pnpm add cowsay --global=true",
        "pnpm add cowsay --config.global=true",
        "pnpm add -Dg cowsay",
        "pnpm add cowsay --global-dir /tmp/g",
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
