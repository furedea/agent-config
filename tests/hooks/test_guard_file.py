"""File-boundary contracts through real hook processes and disposable Git state."""

import json
from pathlib import Path
import subprocess

import pytest

from tests.runtime import CliRunner


SCRIPT = "agents/hooks/guard_file.py"


@pytest.fixture
def protected_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "protected.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": [
                    "~/.claude/hooks/guard_allowed_commands.sh",
                    "~/.claude/hooks/rules/forbidden_commands.json",
                    "~/.claude/settings.json",
                    "~/.claude/custom-protected.json",
                ],
            }
        )
    )
    monkeypatch.setenv("AGENT_PROTECTED_PATH_POLICY", str(path))
    return path


@pytest.mark.parametrize(
    "name,blocked",
    [
        ("~/.claude/hooks/guard_allowed_commands.sh", True),
        ("~/.claude/hooks/rules/forbidden_commands.json", True),
        ("~/.claude/settings.json", True),
        ("~/.claude/custom-protected.json", True),
        ("~/.claude/hooks/custom.sh", False),
        ("agents/hooks/guard_command.py", False),
        ("agents/AGENTS.md", False),
        ("agents/codex/hooks/hook_adapter.py", False),
        ("/tmp/dotfiles/agents/hooks/guard_command.py", False),
        ("src/main.py", False),
        ("", False),
    ],
)
def test_harness_paths(run_cli: CliRunner, protected_policy: Path, name: str, blocked: bool) -> None:
    result = run_cli(SCRIPT, "harness", payload={"tool_name": "MultiEdit", "tool_input": {"file_path": name}})
    assert result.returncode == (2 if blocked else 0)
    if blocked:
        assert "BLOCKED" in result.stderr
        assert "agent harness boundary" in result.stderr
    else:
        assert result.stdout == result.stderr == ""


def test_invalid_harness_policy_fails_closed(run_cli: CliRunner, protected_policy: Path) -> None:
    protected_policy.write_text('{"version":1,"paths":[]}')
    result = run_cli(SCRIPT, "harness", payload={"tool_input": {"file_path": "src/main.py"}})
    assert result.returncode == 2
    assert "invalid protected path policy" in result.stderr


def test_harness_denial_records_metadata(run_cli: CliRunner, protected_policy: Path, isolated_project: Path) -> None:
    result = run_cli(
        SCRIPT,
        "harness",
        payload={
            "cwd": str(isolated_project.parent / "worktree"),
            "session_id": "boundary-session",
            "tool_name": "Edit",
            "tool_input": {"file_path": "~/.claude/settings.json"},
        },
    )
    assert result.returncode == 2
    logs = list(isolated_project.rglob("*.jsonl"))
    assert len(logs) == 1
    row = json.loads(logs[0].read_text())
    assert row["event"] == "Blocked"
    assert row["status"] == "blocked"
    assert row["session"] != "boundary-session"
    assert row["rule"] == "guard_harness_files.sh"
    assert "input" not in row and "reason" not in row


def stage(project: Path, *names: str) -> None:
    for name in names:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("non-sensitive test fixture\n")
    subprocess.run(["git", "add", "--", *names], cwd=project, check=True, capture_output=True)


@pytest.mark.parametrize(
    "name,blocked",
    [
        *[
            (name, True)
            for name in (
                ".env",
                ".env.local",
                ".env.production",
                ".env.development",
                "credentials",
                "credential",
                "secrets",
                "secret",
                "server.pem",
                "private.key",
                "cert.p12",
                "cert.pkcs12",
                "keystore.jks",
                "cert.pfx",
                "id_rsa",
                "id_ed25519",
                ".aws/credentials",
                ".gcp/service-account.json",
                "config/client_secret.json",
            )
        ],
        *[
            (name, False)
            for name in (
                "README.md",
                "src/secret.rs",
                "src/secrets.rs",
                "src/credentials.rs",
                "src/secret_parser.rs",
                "agents/hooks/guard_secret_content.sh",
                "tests/guard_secret_content.bats",
                "src/generation/secret_path_policy.rs",
            )
        ],
    ],
)
def test_staged_filename_policy(run_cli: CliRunner, git_project: Path, name: str, blocked: bool) -> None:
    stage(git_project, name)
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": 'git commit -m "fixture"'}})
    assert result.returncode == (2 if blocked else 0)
    if blocked:
        assert "BLOCKED" in result.stderr
        assert name in result.stderr
    else:
        assert result.stdout == result.stderr == ""


def test_commit_reports_all_sensitive_files(run_cli: CliRunner, git_project: Path) -> None:
    stage(git_project, ".env", "secrets")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": "git commit"}})
    assert result.returncode == 2
    assert ".env" in result.stderr and "secrets" in result.stderr


@pytest.mark.parametrize("command", ["git status", "echo hello", "echo commit", "git commit"])
def test_no_relevant_staged_commit(run_cli: CliRunner, git_project: Path, command: str) -> None:
    if command != "git commit":
        stage(git_project, ".env")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.fixture
def nested_project(git_project: Path) -> Path:
    """A second repository inside the working directory, reached only through cd or git -C."""
    nested = git_project / "nested"
    nested.mkdir()
    subprocess.run(["git", "init", "--quiet", str(nested)], check=True, capture_output=True)
    return nested


@pytest.mark.parametrize(
    "command",
    [
        'cd nested && git commit -m "fixture"',
        'git -C nested commit -m "fixture"',
        "cd nested; git status; git commit",
        'git --git-dir=nested/.git --work-tree=nested commit -m "fixture"',
        'bash -c "cd nested && git commit"',
        "env -C nested git commit",
        "env --chdir=nested git commit",
        "env -u SOME_VAR -C nested git commit",
    ],
)
def test_commits_in_another_repository_check_its_staged_files(
    run_cli: CliRunner, nested_project: Path, command: str
) -> None:
    stage(nested_project, ".env")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 2
    assert ".env" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["(cd nested) && git commit", "cd nested || git commit", "(cd nested; git status); cd . && git commit"],
)
def test_commits_that_may_run_in_the_starting_repository_check_it(
    run_cli: CliRunner, git_project: Path, nested_project: Path, command: str
) -> None:
    stage(git_project, ".env")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 2
    assert ".env" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["git -C nested commit -m $'fixture'", "cd nested && git commit -m $'fixture'"],
)
def test_commits_the_parser_cannot_place_are_left_to_the_user(
    run_cli: CliRunner, nested_project: Path, command: str
) -> None:
    stage(nested_project, ".env")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 0
    decision = json.loads(result.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert "repository" in decision["permissionDecisionReason"]


def test_a_commit_reaching_a_repository_from_outside_any_repository_is_checked(
    run_cli: CliRunner, isolated_project: Path
) -> None:
    nested = isolated_project / "nested"
    subprocess.run(["git", "init", "--quiet", str(nested)], check=True, capture_output=True)
    stage(nested, "README.md")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": "cd nested && git commit"}})
    assert result.returncode == 0
    stage(nested, ".env")
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": "cd nested && git commit"}})
    assert result.returncode == 2


def test_run_time_configuration_values_do_not_hide_the_repository(run_cli: CliRunner, git_project: Path) -> None:
    command = 'git -c user.name="$NAME" commit -m fixture'
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize(
    "command",
    [
        'cd "$REPOSITORY" && git commit',
        'git -C "$REPOSITORY" commit',
        "cd - && git commit",
        "GIT_DIR=nested/.git git commit",
        "env GIT_WORK_TREE=nested git commit",
        "export GIT_INDEX_FILE=other; git commit",
        "env GIT_''INDEX_FILE=other git commit",
        "GIT_\\\nDIR=nested/.git git commit",
        'export GIT_"DIR"=other; git commit',
    ],
)
def test_commits_in_a_repository_known_only_at_run_time_are_blocked(
    run_cli: CliRunner, git_project: Path, command: str
) -> None:
    result = run_cli(SCRIPT, "commit", payload={"tool_input": {"command": command}})
    assert result.returncode == 2
    assert "repository" in result.stderr


@pytest.mark.parametrize("valid", [True, False])
def test_commit_policy_override(run_cli: CliRunner, git_project: Path, valid: bool) -> None:
    stage(git_project, "custom-sensitive.txt")
    policy = git_project / "commit-policy.json"
    rules = [{"pattern": "(^|/)custom-sensitive[.]txt$", "reason": "custom fixture rule"}] if valid else []
    policy.write_text(json.dumps({"version": 1, "rules": rules}))
    result = run_cli(
        SCRIPT,
        "commit",
        payload={"tool_input": {"command": "git commit"}},
        env={"AGENT_SECRET_COMMIT_POLICY": str(policy)},
    )
    assert result.returncode == 2
    assert ("custom fixture rule" if valid else "invalid secret commit policy") in result.stderr


@pytest.mark.parametrize(
    "rules",
    [
        [{"pattern": "x"}],
        [{"pattern": "", "reason": "empty"}],
        [{"pattern": "x", "reason": 1}],
        ["x"],
        [{"pattern": "x", "reason": "ok"}, {"pattern": "[", "reason": "broken regex"}],
    ],
)
def test_malformed_commit_filename_rules_fail_closed(
    run_cli: CliRunner, git_project: Path, rules: list[object]
) -> None:
    stage(git_project, "custom-sensitive.txt")
    policy = git_project / "commit-policy.json"
    policy.write_text(json.dumps({"version": 1, "rules": rules}))
    result = run_cli(
        SCRIPT,
        "commit",
        payload={"tool_input": {"command": "git commit"}},
        env={"AGENT_SECRET_COMMIT_POLICY": str(policy)},
    )
    assert result.returncode == 2
    assert "invalid secret commit policy" in result.stderr
