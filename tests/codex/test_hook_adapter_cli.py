"""Codex protocol translation using actual entry points and isolated policy files."""

import json
from pathlib import Path
import shutil

import pytest

from tests.runtime import CliRunner, REPO_ROOT, StubWriter


SCRIPT = "agents/codex/hooks/hook_adapter.py"


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    root = tmp_path / "harness"
    home.mkdir()
    rules = root / ".claude/hooks/rules"
    rules.mkdir(parents=True)
    (rules / "protected_paths.json").write_text(
        json.dumps(
            {
                "version": 1,
                "paths": ["~/.codex/hooks/adapt_shell_command.sh"],
            }
        )
    )
    shutil.copyfile(REPO_ROOT / "agents/hooks/rules/secret_path_policy.json", rules / "secret_path_policy.json")
    (rules / "secret_content_patterns.json").write_text(
        json.dumps(
            {
                "fixture": {"pattern": "fixture-sensitive-marker", "message": "Fixture detected"},
            }
        )
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_HARNESS_ROOT", str(root))
    for name in ("AGENT_PROTECTED_PATH_POLICY", "AGENT_SECRET_PATH_POLICY", "AGENT_SECRET_CONTENT_PATTERNS"):
        monkeypatch.delenv(name, raising=False)
    return root


def patch_payload(*paths: str) -> dict:
    return {
        "tool_input": {
            "command": "*** Begin Patch\n"
            + "".join(f"*** Update File: {path}\n@@\n-old\n+new\n" for path in paths)
            + "*** End Patch\n"
        }
    }


@pytest.mark.parametrize("field", ["patch", "input", "command"])
def test_patch_carrier_fields_resolve_the_same_targets(run_cli: CliRunner, harness: Path, field: str) -> None:
    body = "*** Begin Patch\n*** Update File: .env.local\n@@\n-old\n+new\n*** End Patch\n"
    result = run_cli(SCRIPT, "paths", "patch", payload={"tool_input": {field: body}})
    assert result.returncode == 2
    assert ".env.local" in result.stderr


def test_conflicting_patch_fields_are_rejected(run_cli: CliRunner, harness: Path) -> None:
    payload = {
        "tool_input": {
            "patch": "*** Begin Patch\n*** Update File: a.py\n*** End Patch\n",
            "command": "*** Begin Patch\n*** Update File: b.py\n*** End Patch\n",
        }
    }
    result = run_cli(SCRIPT, "paths", "patch", payload=payload)
    assert result.returncode == 2
    assert "conflict" in result.stderr.lower()


def test_shell_commands_are_not_patch_paths(run_cli: CliRunner, harness: Path) -> None:
    result = run_cli(SCRIPT, "paths", "patch", payload={"tool_input": {"command": "cat .env.local"}})
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    "arguments",
    [("harness", "--help"), ("lint", "--help"), ("paths",), ("content",), ("shell", "/tmp/arbitrary-hook")],
)
def test_usage(run_cli: CliRunner, arguments: tuple[str, ...]) -> None:
    result = run_cli(SCRIPT, *arguments)
    assert result.returncode == 1
    assert "Usage" in result.stderr


@pytest.mark.parametrize(
    "paths,blocked",
    [
        (("agents/hooks/guard_file.py",), False),
        (("src/main.py",), False),
        (("src/main.py", "~/.codex/hooks/adapt_shell_command.sh"), True),
    ],
)
def test_harness_patch_paths(run_cli: CliRunner, harness: Path, paths: tuple[str, ...], blocked: bool) -> None:
    result = run_cli(SCRIPT, "harness", payload=patch_payload(*paths))
    assert result.returncode == (2 if blocked else 0)
    if blocked:
        assert "BLOCKED" in result.stderr and ".codex/hooks/adapt_shell_command.sh" in result.stderr
    else:
        assert result.stdout == result.stderr == ""


def test_harness_defaults_to_home(run_cli: CliRunner, harness: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(harness))
    monkeypatch.delenv("AGENT_HARNESS_ROOT")
    result = run_cli(SCRIPT, "harness", payload=patch_payload("~/.codex/hooks/adapt_shell_command.sh"))
    assert result.returncode == 2
    assert "agent harness boundary" in result.stderr


@pytest.mark.parametrize(
    "mode,filename,payload",
    [
        (("harness",), "protected_paths.json", patch_payload("src/main.py")),
        (("paths", "command"), "secret_path_policy.json", {"tool_input": {"command": "cat README.md"}}),
    ],
)
def test_missing_policy_fails_closed(
    run_cli: CliRunner, harness: Path, mode: tuple[str, ...], filename: str, payload: dict
) -> None:
    (harness / ".claude/hooks/rules" / filename).unlink()
    result = run_cli(SCRIPT, *mode, payload=payload)
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "mode,payload,blocked_path",
    [
        ("command", {"tool_input": {"command": "cat .env"}}, ".env"),
        ("command", {"tool_input": {"command": "cat ~/.docker/config.json"}}, "~/.docker/config.json"),
        ("command", {"tool_input": {"command": "rg token README.md"}}, ""),
        ("command", {"tool_input": {"command": "cat *.md"}}, ""),
        ("command", {"tool_input": {"command": "cat {.env,README.md}"}}, ".env"),
        ("command", {"tool_input": {"command": "cat .{env,envrc}"}}, ".env"),
        ("command", {"tool_input": {"command": "cat {a,{b,credentials}}.json"}}, "credentials.json"),
        ("command", {"tool_input": {"command": "cat {a,b}.md"}}, ""),
        ("patch", patch_payload(".env.local"), ".env.local"),
        ("patch", {"tool_input": {"file_path": "~/.ssh/config"}}, "~/.ssh/config"),
    ],
)
def test_secret_paths(run_cli: CliRunner, harness: Path, mode: str, payload: dict, blocked_path: str) -> None:
    result = run_cli(SCRIPT, "paths", mode, payload=payload)
    assert result.returncode == (2 if blocked_path else 0)
    if blocked_path:
        assert "BLOCKED" in result.stderr and blocked_path in result.stderr
    else:
        assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    "command,secret,blocked_path",
    [
        ("cat *.json", "api_key.json", "api_key.json"),
        ("cat *.json", "", ""),
        ("jq . *.json", "api_key.json", "api_key.json"),
        ("jq . *.json", "", ""),
        ("cat config/*.json", "config/api_key.json", "config/api_key.json"),
        ("cat config/*.json", "", ""),
        ("cat .*", ".env", ".env"),
        ("cat .*", "", ""),
        ("cat .en*", ".env", ".env"),
        ('cat ".en"*', ".env", ".env"),
        ("cd config && cat *.json", "config/api_key.json", "api_key.json"),
        ("cat {README,api_key}.*", "api_key.json", "api_key.json"),
        ("rg -g '*.json' token", "api_key.json", ""),
        ("cat **/*.json", "nested/deeper/api_key.json", "nested/deeper/api_key.json"),
        ("cat < .en*", ".env", ".env"),
    ],
)
def test_globs_are_judged_by_the_files_they_expand_to(
    run_cli: CliRunner, harness: Path, isolated_project: Path, command: str, secret: str, blocked_path: str
) -> None:
    (isolated_project / "config").mkdir()
    for name in ("package.json", "config/app.json", "README.md", ".gitignore"):
        (isolated_project / name).write_text("{}")
    if secret:
        (isolated_project / secret).parent.mkdir(parents=True, exist_ok=True)
        (isolated_project / secret).write_text("{}")
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": command}})
    assert result.returncode == (2 if blocked_path else 0)
    if blocked_path:
        assert f"Path: {blocked_path}" in result.stderr
    else:
        assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("present", [True, False])
def test_home_globs_expand_against_the_home_directory(run_cli: CliRunner, harness: Path, present: bool) -> None:
    ssh = Path.home() / ".ssh"
    ssh.mkdir()
    (ssh / ("id_rsa" if present else "known_hosts")).write_text("fixture")
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": "cat ~/.ss*/id_rsa"}})
    assert result.returncode == (2 if present else 0)


def fill(directory: Path, count: int) -> None:
    directory.mkdir(parents=True)
    for index in range(count):
        (directory / f"file{index}.txt").touch()


def test_a_glob_walking_too_many_entries_needs_review(
    run_cli: CliRunner, harness: Path, isolated_project: Path
) -> None:
    fill(isolated_project / "data", 10001)
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": "cat **/*.json"}})
    assert result.returncode == 2
    assert "review" in result.stderr.lower()


def test_a_recursive_glob_skips_dependency_directories(
    run_cli: CliRunner, harness: Path, isolated_project: Path
) -> None:
    fill(isolated_project / "node_modules/package", 10001)
    (isolated_project / "src").mkdir()
    (isolated_project / "src/app.json").write_text("{}")
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": "cat **/*.json"}})
    assert result.returncode == 0


@pytest.mark.parametrize("variable", ["$HOME", "${HOME}"])
def test_home_variable_globs_expand_against_the_home_directory(
    run_cli: CliRunner, harness: Path, variable: str
) -> None:
    ssh = Path.home() / ".ssh"
    ssh.mkdir()
    (ssh / "id_rsa").write_text("fixture")
    payload = {"tool_input": {"command": f"cat {variable}/.ssh/id_*"}}
    result = run_cli(SCRIPT, "paths", "command", payload=payload)
    assert result.returncode == 2


def test_brace_expansions_beyond_the_limit_need_review(run_cli: CliRunner, harness: Path) -> None:
    command = "cat {" + ",".join(f"safe{index}" for index in range(256)) + ",.env}"
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": command}})
    assert result.returncode == 2
    assert "review" in result.stderr.lower()


@pytest.mark.parametrize("command", ['cd "$DIR" && cat *.json', "cd - && cat .*", "cat $DIR/*.json"])
def test_globs_in_an_unknown_directory_need_review(run_cli: CliRunner, harness: Path, command: str) -> None:
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": command}})
    assert result.returncode == 2
    assert "review" in result.stderr.lower()


def test_an_unknown_directory_does_not_matter_without_a_glob(run_cli: CliRunner, harness: Path) -> None:
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"command": 'cd "$DIR" && cat README.md'}})
    assert result.returncode == 0


@pytest.mark.parametrize("field", ["command", "cmd"])
def test_heredoc_denial_omits_the_body(run_cli: CliRunner, harness: Path, field: str) -> None:
    command = "bash <<SH\n" + "echo body_must_not_be_repeated $X\n" * 100 + "SH\n"
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {field: command}})
    assert result.returncode == 2
    assert "heredoc" in result.stderr.lower()
    assert "bash <<SH" in result.stderr
    assert "omitted" in result.stderr.lower()
    assert "body_must_not_be_repeated" not in result.stderr
    assert len(result.stderr) < 500


def test_long_command_denial_has_a_bounded_preview(run_cli: CliRunner, harness: Path) -> None:
    command = "echo " + "x" * 1000 + " $'uninspectable'"
    result = run_cli(SCRIPT, "paths", "command", payload={"tool_input": {"cmd": command}})
    assert result.returncode == 2
    assert "BLOCKED:" in result.stderr
    assert "echo " in result.stderr
    assert "omitted" in result.stderr.lower()
    assert len(result.stderr) < 500


@pytest.mark.parametrize("field", ["command", "cmd"])
@pytest.mark.parametrize("command,blocked", [("git reset --hard", True), ("git status", False)])
def test_shell_payload_fields(run_cli: CliRunner, field: str, command: str, blocked: bool) -> None:
    result = run_cli(SCRIPT, "shell", "git", payload={"tool_input": {field: command}})
    assert result.returncode == (2 if blocked else 0)
    if blocked:
        assert "BLOCKED" in result.stderr and command in result.stderr
    else:
        assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("fail", [True, False])
def test_lint_resolves_payload_cwd_and_suppresses_noise(
    run_cli: CliRunner, tmp_path: Path, executable: StubWriter, fail: bool
) -> None:
    executable(
        "ruff",
        """
        import os, sys
        if "--output-format=concise" in sys.argv and os.environ["LINT_FIXTURE_FAIL"] == "1":
            print("ruff: F821 undefined name")
            sys.exit(1)
        print("environment noise", file=sys.stderr)
    """,
    )
    project = tmp_path / "nested"
    project.mkdir()
    (project / "pyproject.toml").write_text("[tool.ruff]\n[tool.ruff.format]\n")
    (project / "x.py").write_text("x = 1\n")
    payload = patch_payload("x.py") | {"cwd": str(project)}
    result = run_cli(SCRIPT, "lint", payload=payload, env={"LINT_FIXTURE_FAIL": str(int(fail))})
    assert result.returncode == 0
    assert result.stderr == ""
    if fail:
        row = json.loads(result.stdout)
        assert row["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "F821" in row["hookSpecificOutput"]["additionalContext"]
        assert str(project / "x.py") in row["hookSpecificOutput"]["additionalContext"]
    else:
        assert result.stdout == ""
    assert "environment noise" not in result.stdout


@pytest.mark.parametrize(
    "mode,text,blocked",
    [
        ("prompt", "fixture-sensitive-marker", True),
        ("prompt", "safe prompt", False),
        (
            "apply-patch",
            "*** Begin Patch\n*** Update File: x.txt\n@@\n-old\n+fixture-sensitive-marker\n*** End Patch",
            True,
        ),
        (
            "apply-patch",
            "*** Begin Patch\n*** Update File: x.txt\n@@\n-fixture-sensitive-marker\n+safe\n*** End Patch",
            False,
        ),
    ],
)
def test_content_translation(run_cli: CliRunner, harness: Path, mode: str, text: str, blocked: bool) -> None:
    payload = {"prompt": text} if mode == "prompt" else {"tool_input": {"command": text}}
    result = run_cli(SCRIPT, "content", mode, payload=payload)
    assert result.returncode == 0
    assert result.stderr == ""
    if blocked:
        decision = json.loads(result.stdout)
        assert "Fixture detected" in result.stdout
        if mode == "prompt":
            assert decision["decision"] == "block"
        else:
            assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    else:
        assert result.stdout == ""


def test_a_new_suppression_is_denied_in_codex_since_its_hooks_cannot_ask(run_cli: CliRunner, harness: Path) -> None:
    body = "*** Begin Patch\n*** Update File: src/app.py\n@@\n-x = 1\n+x = 1  # noqa: E501\n*** End Patch\n"
    result = run_cli(
        SCRIPT, "content", "suppression", payload={"tool_name": "apply_patch", "tool_input": {"input": body}}
    )
    assert result.returncode == 2
    assert "suppression" in result.stderr
