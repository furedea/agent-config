"""dsh protocol translation using actual entry points and isolated policy files."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.runtime import CliRunner, REPO_ROOT, StubWriter


SCRIPT = "agents/dsh/hooks/hook_adapter.py"
PRE = "tools/pre-execute"
POST = "tools/post-execute"


@pytest.fixture
def harness(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = isolated_project / "home"
    root = isolated_project / "harness"
    home.mkdir()
    rules = root / ".claude/hooks/rules"
    rules.mkdir(parents=True)
    (rules / "protected_paths.json").write_text(json.dumps({"version": 1, "paths": ["~/.dsh/hooks/hook_adapter.py"]}))
    shutil.copyfile(REPO_ROOT / "agents/hooks/rules/secret_path_policy.json", rules / "secret_path_policy.json")
    shutil.copyfile(REPO_ROOT / "agents/hooks/rules/secret_commit_policy.json", rules / "secret_commit_policy.json")
    shutil.copyfile(REPO_ROOT / "agents/hooks/rules/forbidden_commands.json", rules / "forbidden_commands.json")
    shutil.copyfile(REPO_ROOT / "agents/hooks/rules/allowed_commands.json", rules / "allowed_commands.json")
    (rules / "secret_content_patterns.json").write_text(
        json.dumps({"fixture": {"pattern": "fixture-sensitive-marker", "message": "Fixture detected"}})
    )
    (rules / "command_permissions.json").write_text((REPO_ROOT / "agents/command_permissions.json").read_text())
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_HARNESS_ROOT", str(root))
    for name in (
        "AGENT_PROTECTED_PATH_POLICY",
        "AGENT_SECRET_PATH_POLICY",
        "AGENT_SECRET_CONTENT_PATTERNS",
        "AGENT_COMMAND_PERMISSIONS",
        "AGENT_ALLOWED_COMMAND_RULES",
        "AGENT_FORBIDDEN_COMMAND_RULES",
    ):
        monkeypatch.delenv(name, raising=False)
    return root


@pytest.fixture
def project(isolated_project: Path) -> Path:
    root = isolated_project / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(root)], check=True)
    return root


@pytest.fixture
def manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "hooks.json"
    monkeypatch.setenv("AGENT_HARNESS_DSH_MANIFEST", str(path))
    return path


@pytest.mark.parametrize(
    "arguments",
    [
        ("native", "pre-tool-use"),
        ("audit", "tool"),
        ("paths",),
        ("content",),
        ("dispatch",),
        ("shell", "/tmp/arbitrary-hook"),
    ],
)
def test_usage(run_cli: CliRunner, arguments: tuple[str, ...]) -> None:
    result = run_cli(SCRIPT, *arguments)
    assert result.returncode == 1
    assert "Usage" in result.stderr


@pytest.mark.parametrize(
    "command,blocked",
    [("git reset --hard", True), ("git status", False)],
)
def test_shell_git_guard_reads_the_bash_tool(run_cli: CliRunner, project: Path, command: str, blocked: bool) -> None:
    payload = {"tool_name": "bash", "tool_input": {"command": command}, "cwd": str(project)}
    result = run_cli(SCRIPT, "shell", "git", payload=payload, cwd=project)
    assert result.returncode == (2 if blocked else 0)
    if blocked:
        assert "BLOCKED" in result.stderr


@pytest.mark.parametrize("relative", [False, True])
def test_commit_guard_checks_the_repository_of_the_bash_workdir(
    run_cli: CliRunner, project: Path, relative: bool
) -> None:
    other = project / "other"
    other.mkdir()
    subprocess.run(["git", "init", "--quiet", str(other)], check=True, capture_output=True)
    (other / ".env").write_text("SECRET=1\n")
    subprocess.run(["git", "-C", str(other), "add", ".env"], check=True, capture_output=True)
    values = {"command": "git commit -m x", "workdir": "other" if relative else str(other)}
    payload = {"tool_name": "bash", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "shell", "commit", payload=payload, cwd=project)
    assert result.returncode == 2
    assert ".env" in result.stderr


def test_dispatch_applies_a_relative_workdir_only_once(run_cli: CliRunner, project: Path, manifest: Path) -> None:
    (project / "packages").mkdir()
    adapter = REPO_ROOT / SCRIPT
    manifest.write_text(
        json.dumps({"hooks": {PRE: [{"matcher": "^bash$", "hooks": [{"command": f'"{adapter}" paths command'}]}]}})
    )
    values = {"command": "ls", "workdir": "packages"}
    payload = {"hook_event_name": PRE, "tool_name": "bash", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "dispatch", PRE, payload=payload, cwd=project)
    assert result.returncode == 0
    assert result.stderr == ""


def test_commit_guard_uses_the_payload_cwd_without_a_workdir(run_cli: CliRunner, project: Path) -> None:
    payload = {"tool_name": "bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(project)}
    result = run_cli(SCRIPT, "shell", "commit", payload=payload, cwd=project)
    assert result.returncode == 0


def test_forbidden_command_is_blocked(run_cli: CliRunner, project: Path) -> None:
    payload = {"tool_name": "bash", "tool_input": {"command": "rm -rf /"}, "cwd": str(project)}
    result = run_cli(SCRIPT, "shell", "forbidden", payload=payload, cwd=project)
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr


@pytest.mark.parametrize(
    "mode,payload,blocked_path",
    [
        ("command", {"tool_name": "bash", "tool_input": {"command": "cat .env"}}, ".env"),
        ("patch", {"tool_name": "write", "tool_input": {"file_path": "~/.ssh/config"}}, "~/.ssh/config"),
        ("patch", {"tool_name": "write", "tool_input": {"path": "~/.ssh/config"}}, "~/.ssh/config"),
        ("patch", {"tool_name": "edit", "tool_input": {"file_path": "~/.ssh/config"}}, "~/.ssh/config"),
        (
            "patch",
            {"tool_name": "str_replace_editor", "tool_input": {"path": "~/.ssh/config", "command": "str_replace"}},
            "~/.ssh/config",
        ),
    ],
)
@pytest.mark.usefixtures("harness")
def test_secret_paths_block_with_dsh_fields(run_cli: CliRunner, mode: str, payload: dict, blocked_path: str) -> None:
    result = run_cli(SCRIPT, "paths", mode, payload=payload)
    assert result.returncode == 2
    assert blocked_path in result.stderr


def patch_input(*lines: str) -> str:
    return "\n".join(["*** Begin Patch", *lines, "*** End Patch"]) + "\n"


@pytest.mark.usefixtures("harness")
def test_str_replace_editor_view_is_scanned_like_read(run_cli: CliRunner, project: Path) -> None:
    (project / "notes.txt").write_text("use fixture-sensitive-marker here\n")
    values = {"command": "view", "path": "notes.txt"}
    payload = {"tool_name": "str_replace_editor", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "content", "read", payload=payload, cwd=project)
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"


@pytest.mark.usefixtures("harness")
def test_str_replace_editor_view_is_not_held_to_the_harness_write_boundary(run_cli: CliRunner) -> None:
    values = {"command": "view", "path": "~/.dsh/hooks/hook_adapter.py"}
    result = run_cli(SCRIPT, "harness", payload={"tool_name": "str_replace_editor", "tool_input": values})
    assert result.returncode == 0
    assert result.stderr == ""


@pytest.mark.parametrize("command", ["create", "str_replace", "insert"])
@pytest.mark.usefixtures("harness")
def test_str_replace_editor_mutations_stay_inside_the_harness_boundary(run_cli: CliRunner, command: str) -> None:
    values = {"command": command, "path": "~/.dsh/hooks/hook_adapter.py"}
    result = run_cli(SCRIPT, "harness", payload={"tool_name": "str_replace_editor", "tool_input": values})
    assert result.returncode == 2
    assert "agent harness boundary" in result.stderr


@pytest.mark.parametrize("tool", ["write", "edit", "str_replace_editor", "apply_patch"])
def test_a_failed_edit_is_not_linted(run_cli: CliRunner, tmp_path: Path, executable: StubWriter, tool: str) -> None:
    executable(
        "ruff",
        """
        import sys
        if "--output-format=concise" in sys.argv:
            print("ruff: F821 undefined name")
            sys.exit(1)
        """,
    )
    project = tmp_path / "failed-repo"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n")
    values = {"file_path": "x.py", "input": patch_input("*** Update File: x.py", "@@", "-x = 1", "+x = 2")}
    payload = {"tool_name": tool, "tool_input": values, "tool_response": {"isError": True}, "cwd": str(project)}
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert result.stdout == ""

    payload["tool_response"] = {"isError": False}
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert "F821" in json.loads(result.stdout)["systemMessage"]


def test_str_replace_editor_view_is_not_linted(run_cli: CliRunner, tmp_path: Path, executable: StubWriter) -> None:
    executable(
        "ruff",
        """
        import sys
        if "--output-format=concise" in sys.argv:
            print("ruff: F821 undefined name")
            sys.exit(1)
        """,
    )
    project = tmp_path / "view-repo"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n")
    values = {"command": "view", "path": str(project / "x.py")}
    payload = {"tool_name": "str_replace_editor", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("command", ["create", "str_replace", "insert"])
def test_str_replace_editor_mutations_are_not_read_scanned(run_cli: CliRunner, project: Path, command: str) -> None:
    (project / "notes.txt").write_text("use fixture-sensitive-marker here\n")
    values = {"command": command, "path": "notes.txt"}
    payload = {"tool_name": "str_replace_editor", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "content", "read", payload=payload, cwd=project)
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize("field", ["input", "patch", "command"])
@pytest.mark.usefixtures("harness")
def test_apply_patch_secret_paths_are_blocked(run_cli: CliRunner, field: str) -> None:
    body = patch_input("*** Update File: ~/.ssh/config", "@@", "-a", "+b")
    payload = {"tool_name": "apply_patch", "tool_input": {field: body}}
    result = run_cli(SCRIPT, "paths", "patch", payload=payload)
    assert result.returncode == 2
    assert ".ssh" in result.stderr


@pytest.mark.usefixtures("harness")
def test_apply_patch_harness_boundary_protects_the_adapter(run_cli: CliRunner) -> None:
    body = patch_input("*** Update File: ~/.dsh/hooks/hook_adapter.py", "@@", "-a", "+b")
    payload = {"tool_name": "apply_patch", "tool_input": {"input": body}}
    result = run_cli(SCRIPT, "harness", payload=payload)
    assert result.returncode == 2
    assert "agent harness boundary" in result.stderr


@pytest.mark.usefixtures("harness")
def test_apply_patch_added_text_is_scanned_for_secret_markers(run_cli: CliRunner, project: Path) -> None:
    body = patch_input("*** Add File: notes.txt", "+fixture-sensitive-marker")
    payload = {"tool_name": "apply_patch", "tool_input": {"input": body}, "cwd": str(project)}
    result = run_cli(SCRIPT, "content", "apply-patch", payload=payload, cwd=project)
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"


def test_lint_covers_apply_patch_targets(run_cli: CliRunner, tmp_path: Path, executable: StubWriter) -> None:
    executable(
        "ruff",
        """
        import sys
        if "--output-format=concise" in sys.argv:
            print("ruff: F821 undefined name")
            sys.exit(1)
        """,
    )
    project = tmp_path / "patch-repo"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n")
    body = patch_input("*** Update File: x.py", "@@", "-x = 1", "+x = 2")
    payload = {"tool_name": "apply_patch", "tool_input": {"input": body}, "cwd": str(project)}
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert "F821" in json.loads(result.stdout)["systemMessage"]


@pytest.mark.parametrize("tool", ["write", "edit", "str_replace_editor"])
@pytest.mark.usefixtures("harness")
def test_harness_boundary_protects_the_adapter_for_every_edit_tool(run_cli: CliRunner, tool: str) -> None:
    payload = {"tool_name": tool, "tool_input": {"file_path": "~/.dsh/hooks/hook_adapter.py"}}
    result = run_cli(SCRIPT, "harness", payload=payload)
    assert result.returncode == 2
    assert "agent harness boundary" in result.stderr


@pytest.mark.parametrize("tool", ["read", "read_image"])
@pytest.mark.usefixtures("harness")
def test_content_read_guards_secret_markers_in_read_targets(run_cli: CliRunner, project: Path, tool: str) -> None:
    (project / "notes.txt").write_text("use fixture-sensitive-marker here\n")
    payload = {"tool_name": tool, "tool_input": {"file_path": "notes.txt"}, "cwd": str(project)}
    result = run_cli(SCRIPT, "content", "read", payload=payload, cwd=project)
    assert result.returncode == 0
    decision = json.loads(result.stdout)
    assert decision["decision"] == "block"
    assert "Fixture detected" in decision["reason"]


@pytest.mark.parametrize(
    "values",
    [
        {"content": "fixture-sensitive-marker"},
        {"new_string": "fixture-sensitive-marker"},
        {"command": "create", "path": "/x", "file_text": "fixture-sensitive-marker"},
        {"command": "str_replace", "path": "/x", "old_str": "a", "new_str": "fixture-sensitive-marker"},
        {"command": "insert", "path": "/x", "insert_line": 0, "new_str": "fixture-sensitive-marker", "old_str": None},
    ],
)
@pytest.mark.usefixtures("harness")
def test_content_write_guards_secret_markers_in_every_dsh_edit_field(
    run_cli: CliRunner, project: Path, values: dict
) -> None:
    payload = {"tool_name": "str_replace_editor", "tool_input": values, "cwd": str(project)}
    result = run_cli(SCRIPT, "content", "write", payload=payload, cwd=project)
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"


def test_lint_returns_diagnostics_as_a_system_message(
    run_cli: CliRunner, tmp_path: Path, executable: StubWriter
) -> None:
    executable(
        "ruff",
        """
        import sys
        if "--output-format=concise" in sys.argv:
            print("ruff: F821 undefined name")
            sys.exit(1)
        """,
    )
    project = tmp_path / "lint-repo"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n")
    payload = {
        "tool_name": "write",
        "tool_input": {"file_path": "x.py"},
        "cwd": str(project),
    }
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert result.stderr == ""
    row = json.loads(result.stdout)
    assert list(row) == ["systemMessage"]
    assert "F821" in row["systemMessage"]
    assert str(project / "x.py") in row["systemMessage"]


def test_lint_is_silent_without_diagnostics(run_cli: CliRunner, tmp_path: Path) -> None:
    payload = {"tool_name": "write", "tool_input": {"file_path": "notes.txt"}, "cwd": str(tmp_path)}
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert result.stdout == ""


def test_dispatch_blocks_through_the_manifest(
    run_cli: CliRunner, project: Path, manifest: Path, tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker.py"
    blocker.write_text(
        "import json, sys\n"
        "payload = json.load(sys.stdin)\n"
        "print(json.dumps({'decision': 'block', 'reason': 'manifest blocked ' + payload['tool_name']}))\n"
    )
    manifest.write_text(
        json.dumps({"hooks": {PRE: [{"matcher": "^bash$", "hooks": [{"command": f"{sys.executable} {blocker}"}]}]}})
    )
    payload = {"hook_event_name": PRE, "tool_name": "bash", "tool_input": {"command": "x"}, "cwd": str(project)}

    result = run_cli(SCRIPT, "dispatch", PRE, payload=payload, cwd=project)
    assert result.returncode == 0
    assert json.loads(result.stdout)["reason"] == "manifest blocked bash"

    payload["tool_name"] = "read"
    result = run_cli(SCRIPT, "dispatch", PRE, payload=payload, cwd=project)
    assert result.returncode == 0
    assert result.stdout == ""


def test_dispatch_returns_the_lint_system_message_after_a_write(
    run_cli: CliRunner, tmp_path: Path, manifest: Path, executable: StubWriter
) -> None:
    executable(
        "ruff",
        """
        import sys
        if "--output-format=concise" in sys.argv:
            print("ruff: F821 undefined name")
            sys.exit(1)
        """,
    )
    project = tmp_path / "post-repo"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n")
    adapter = REPO_ROOT / SCRIPT
    manifest.write_text(
        json.dumps({"hooks": {POST: [{"matcher": "^(write|edit)$", "hooks": [{"command": f'"{adapter}" lint'}]}]}})
    )
    payload = {
        "hook_event_name": POST,
        "tool_name": "write",
        "tool_input": {"file_path": "x.py"},
        "tool_response": {},
        "cwd": str(project),
    }
    result = run_cli(SCRIPT, "dispatch", POST, payload=payload)
    assert result.returncode == 0
    assert "F821" in json.loads(result.stdout)["systemMessage"]


def test_dispatch_propagates_exit_two(run_cli: CliRunner, project: Path, manifest: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "blocker.py"
    blocker.write_text("import sys\nprint('nope', file=sys.stderr)\nsys.exit(2)\n")
    manifest.write_text(json.dumps({"hooks": {PRE: [{"hooks": [{"command": f"{sys.executable} {blocker}"}]}]}}))

    result = run_cli(SCRIPT, "dispatch", PRE, payload={}, cwd=project)
    assert result.returncode == 2
    assert "nope" in result.stderr
