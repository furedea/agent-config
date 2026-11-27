"""Antigravity protocol translation using the actual entry point and isolated policy files."""

import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from tests.runtime import REPO_ROOT, CliRunner, load_script_module

pytestmark = pytest.mark.usefixtures("harness")

SCRIPT = "agents/antigravity/hooks/hook_adapter.py"
CONVERSATION = "3f1c0a52-6a41-4d7e-9a35-2f2d5b2b7c11"


@pytest.fixture
def harness(isolated_project: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = isolated_project / "home"
    root = isolated_project / "harness"
    home.mkdir()
    rules = root / ".claude/hooks/rules"
    rules.mkdir(parents=True)
    protected = ["~/.gemini/config/hooks/hook_adapter.py"]
    (rules / "protected_paths.json").write_text(json.dumps({"version": 1, "paths": protected}))
    for name in (
        "secret_path_policy",
        "secret_commit_policy",
        "forbidden_commands",
        "allowed_commands",
    ):
        shutil.copyfile(REPO_ROOT / f"agents/hooks/rules/{name}.json", rules / f"{name}.json")
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
def adapter() -> ModuleType:
    return load_script_module(SCRIPT, "antigravity_hook_adapter_under_test")


def tool_payload(project: Path, name: str, args: dict, event: str = "PreToolUse") -> dict:
    return {
        "conversationId": CONVERSATION,
        "cwd": str(project),
        "hookEventName": event,
        "toolCall": {"id": "toolu_01", "name": name, "args": args},
        "stepIdx": 3,
    }


def stdout_object(result: subprocess.CompletedProcess[str]) -> dict:
    """The provider reads exactly one JSON object from stdout."""
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "arguments",
    [
        ("native", "session-end"),
        ("audit", "unknown"),
        ("audit", "tool"),
        ("paths",),
        ("content",),
        ("dispatch", "PreToolUse"),
        ("shell", "x"),
    ],
)
def test_usage(run_cli: CliRunner, arguments: tuple[str, ...]) -> None:
    result = run_cli(SCRIPT, *arguments)
    assert result.returncode == 1
    assert "Usage" in result.stderr


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("run_command", {"CommandLine": "ls", "Cwd": "/w"}, {"command": "ls", "workdir": "/w"}),
        ("read_file", {"Path": "/a.txt"}, {"file_path": "/a.txt"}),
        ("view_file", {"AbsolutePath": "/a.txt", "StartLine": 1}, {"file_path": "/a.txt", "StartLine": 1}),
        ("write_file", {"Path": "/a.txt", "Content": "x"}, {"file_path": "/a.txt", "content": "x"}),
        ("write_to_file", {"TargetFile": "/a.txt", "CodeContent": "x"}, {"file_path": "/a.txt", "content": "x"}),
        (
            "replace_file_content",
            {"TargetFile": "/a.txt", "ReplacementContent": "y"},
            {"file_path": "/a.txt", "new_string": "y"},
        ),
        (
            "multi_replace_file_content",
            {"TargetFile": "/a.txt", "ReplacementChunks": [{"ReplacementContent": "a"}, {"ReplacementContent": "b"}]},
            {"file_path": "/a.txt", "new_string": "ab"},
        ),
    ],
)
def test_arguments_are_renamed_to_the_shared_field_names(
    adapter: ModuleType, name: str, args: dict, expected: dict
) -> None:
    values = adapter.read({"toolCall": {"name": name, "args": args}})["tool_input"]
    assert expected.items() <= values.items()


@pytest.mark.parametrize(
    "native,shared",
    [
        ("run_command", "Bash"),
        ("read_file", "Read"),
        ("view_file", "Read"),
        ("write_file", "Write"),
        ("write_to_file", "Write"),
        ("edit_file", "Edit"),
        ("replace_file_content", "Edit"),
        ("multi_replace_file_content", "Edit"),
        ("search_web", "WebSearch"),
        ("read_url_content", "WebFetch"),
        ("mcp_server_tool", "mcp_server_tool"),
        ("browser_click", "browser_click"),
    ],
)
def test_tool_names_map_to_the_shared_names_and_others_pass_through(
    adapter: ModuleType, native: str, shared: str
) -> None:
    context = adapter.ADAPTER.normalized(adapter.read({"toolCall": {"name": native, "args": {}}}))
    assert context["tool_name"] == shared
    assert context["provider"] == "antigravity"


def test_common_fields_are_normalized(adapter: ModuleType) -> None:
    payload = {
        "conversationId": CONVERSATION,
        "cwd": "/work",
        "hookEventName": "PostToolUse",
        "lastUserInput": "fix it",
        "toolCall": {"name": "run_command", "args": {"CommandLine": "false"}},
        "error": "exit status 1",
    }
    context = adapter.ADAPTER.normalized(adapter.read(payload))
    assert context["session_id"] == CONVERSATION
    assert context["cwd"] == "/work"
    assert context["hook_event_name"] == "PostToolUse"
    assert context["prompt"] == "fix it"
    assert context["tool_response"] == {"isError": True, "error": "exit status 1"}


def test_the_payload_cwd_wins_over_the_hook_process_directory(
    run_cli: CliRunner, project: Path, isolated_project: Path
) -> None:
    (project / ".env").write_text("SECRET=1\n")
    subprocess.run(["git", "-C", str(project), "add", ".env"], check=True)
    payload = tool_payload(project, "run_command", {"CommandLine": "git commit -m x"})
    result = run_cli(SCRIPT, "shell", "commit", payload=payload, cwd=isolated_project)
    assert result.returncode == 0
    assert ".env" in result.stderr


@pytest.mark.parametrize("spelling", ["continuationActive", "continuation_active"])
@pytest.mark.parametrize("active", [True, False])
def test_stop_continuation_is_read_from_either_spelling(adapter: ModuleType, spelling: str, active: bool) -> None:
    assert adapter.read({spelling: active})["stop_hook_active"] is active


@pytest.mark.parametrize(
    "event,result,expected",
    [
        ("PreToolUse", {}, {"decision": "allow"}),
        ("PostToolUse", {"decision": "block", "reason": "x"}, {}),
        ("Stop", {}, {}),
        ("Stop", {"systemMessage": "note"}, {}),
        ("Stop", {"decision": "block", "reason": "fix"}, {"decision": "continue", "reason": "fix"}),
        ("SessionStart", {}, {}),
        (
            "SessionStart",
            {"hookSpecificOutput": {"additionalContext": "ctx"}},
            {"injectSteps": [{"systemMessage": {"systemMessage": "ctx"}}]},
        ),
    ],
)
def test_results_are_encoded_for_the_event(adapter: ModuleType, event: str, result: dict, expected: dict) -> None:
    assert adapter.output(event, result) == expected


@pytest.mark.parametrize(
    "decision,expected",
    [("deny", "deny"), ("ask", "force_ask")],
)
def test_pre_tool_use_refusals_never_use_the_cacheable_ask(adapter: ModuleType, decision: str, expected: str) -> None:
    result = {"hookSpecificOutput": {"permissionDecision": decision, "permissionDecisionReason": "why"}}
    assert adapter.output("PreToolUse", result) == {"decision": expected, "reason": "why"}


def test_a_forbidden_command_is_denied_on_stdout_and_stderr(run_cli: CliRunner, project: Path) -> None:
    payload = tool_payload(project, "run_command", {"CommandLine": "rm -rf /"})
    result = run_cli(SCRIPT, "shell", "forbidden", payload=payload)
    assert result.returncode == 0
    assert stdout_object(result)["decision"] == "deny"
    assert "BLOCKED" in stdout_object(result)["reason"]
    assert "BLOCKED" in result.stderr


def test_a_command_that_needs_review_is_force_asked(run_cli: CliRunner, project: Path) -> None:
    payload = tool_payload(project, "run_command", {"CommandLine": "git push origin $'topic'"})
    result = run_cli(SCRIPT, "shell", "git", payload=payload)
    assert result.returncode == 0
    output = stdout_object(result)
    assert output["decision"] == "force_ask"
    assert "review" in output["reason"]


def test_a_guard_that_finds_nothing_answers_allow_because_an_empty_object_is_denied(
    run_cli: CliRunner, project: Path
) -> None:
    payload = tool_payload(project, "run_command", {"CommandLine": "git status"})
    result = run_cli(SCRIPT, "shell", "git", payload=payload)
    assert result.returncode == 0
    assert stdout_object(result) == {"decision": "allow"}


@pytest.mark.parametrize(
    "name,args",
    [
        ("view_file", {"AbsolutePath": "~/.ssh/config"}),
        ("write_file", {"Path": "~/.ssh/config", "Content": "x"}),
        ("edit_file", {"Path": "~/.ssh/config"}),
    ],
)
def test_secret_paths_are_denied_for_every_file_tool(run_cli: CliRunner, project: Path, name: str, args: dict) -> None:
    result = run_cli(SCRIPT, "paths", "patch", payload=tool_payload(project, name, args))
    assert result.returncode == 0
    assert stdout_object(result)["decision"] == "deny"


def test_secret_paths_in_a_command_are_denied(run_cli: CliRunner, project: Path) -> None:
    result = run_cli(
        SCRIPT, "paths", "command", payload=tool_payload(project, "run_command", {"CommandLine": "cat .env"})
    )
    assert result.returncode == 0
    assert stdout_object(result)["decision"] == "deny"


def test_editing_the_hook_adapter_is_denied_by_the_harness_guard(run_cli: CliRunner, project: Path) -> None:
    args = {"TargetFile": "~/.gemini/config/hooks/hook_adapter.py", "ReplacementContent": "x"}
    result = run_cli(SCRIPT, "harness", payload=tool_payload(project, "replace_file_content", args))
    assert result.returncode == 0
    assert "agent harness boundary" in stdout_object(result)["reason"]


def test_sensitive_content_is_denied_not_blocked(run_cli: CliRunner, project: Path) -> None:
    args = {"Path": str(project / "a.txt"), "Content": "fixture-sensitive-marker"}
    result = run_cli(SCRIPT, "content", "write", payload=tool_payload(project, "write_file", args))
    assert stdout_object(result) == {"decision": "deny", "reason": "BLOCKED: Fixture detected (fixture)"}


def test_a_new_suppression_is_force_asked(run_cli: CliRunner, project: Path) -> None:
    args = {"Path": "src/app.py", "Content": "x = 1  # noqa: E501\n"}
    result = run_cli(SCRIPT, "content", "suppression", payload=tool_payload(project, "write_file", args))
    assert result.returncode == 0
    assert stdout_object(result)["decision"] == "force_ask"


def test_session_start_asks_nothing_and_reports_the_verification_record(run_cli: CliRunner, project: Path) -> None:
    payload = {"conversationId": CONVERSATION, "cwd": str(project), "hookEventName": "SessionStart"}
    result = run_cli(SCRIPT, "native", "session-start", payload=payload)
    assert result.returncode == 0
    [step] = stdout_object(result)["injectSteps"]
    assert "Verification record:" in step["systemMessage"]["systemMessage"]


@pytest.mark.parametrize(
    "spelling,decision", [(None, "continue"), ("continuationActive", None), ("continuation_active", None)]
)
def test_stop_continues_once_then_lets_the_agent_stop(
    run_cli: CliRunner, project: Path, spelling: str | None, decision: str | None
) -> None:
    """An unresolved verification continues the agent; a continuation already under way must not loop."""
    payload = {"conversationId": CONVERSATION, "cwd": str(project), "hookEventName": "Stop", "executionNum": 1}
    if spelling:
        payload[spelling] = True
    result = run_cli(SCRIPT, "native", "stop", payload=payload)
    assert result.returncode == 0
    assert stdout_object(result).get("decision") == decision


def test_lint_never_blocks_the_agent_through_post_tool_use(run_cli: CliRunner, project: Path) -> None:
    source = project / "bad.py"
    source.write_text("import os\n")
    payload = tool_payload(project, "write_file", {"Path": str(source), "Content": "import os\n"}, "PostToolUse")
    result = run_cli(SCRIPT, "lint", payload=payload)
    assert result.returncode == 0
    assert stdout_object(result) == {}


@pytest.mark.parametrize("raw", ["{", "null", "[]"])
def test_non_object_payloads_are_denied(run_cli: CliRunner, raw: str) -> None:
    result = run_cli(SCRIPT, "shell", "git", payload=raw)
    assert result.returncode == 0
    assert stdout_object(result)["decision"] == "deny"


@pytest.mark.parametrize(
    "args",
    [
        {"Path": "/safe.txt", "TargetFile": "~/.ssh/config"},
        {"file_path": "/safe.txt", "AbsolutePath": "~/.ssh/config"},
        {"Content": "a", "CodeContent": "b"},
    ],
)
def test_ambiguous_arguments_are_denied_instead_of_guarding_only_one(
    run_cli: CliRunner, project: Path, args: dict
) -> None:
    result = run_cli(SCRIPT, "paths", "patch", payload=tool_payload(project, "write_file", args))
    assert result.returncode == 0
    assert "ambiguous" in stdout_object(result)["reason"]


def test_replacement_chunks_add_to_the_single_replacement(adapter: ModuleType) -> None:
    args = {"ReplacementContent": "a", "ReplacementChunks": [{"ReplacementContent": "b"}]}
    assert adapter.shared_arguments(args)["new_string"] == "ab"


@pytest.mark.parametrize(
    "arguments",
    [("lint",)],
)
def test_a_failing_non_guard_command_answers_an_empty_object_and_keeps_exit_status_2(
    run_cli: CliRunner, project: Path, arguments: tuple[str, ...]
) -> None:
    args = {"Path": "/safe.txt", "TargetFile": "/other.txt"}
    payload = tool_payload(project, "write_file", args, "PostToolUse")
    result = run_cli(SCRIPT, *arguments, payload=payload)
    assert result.returncode == 2
    assert stdout_object(result) == {}
    assert "ambiguous" in result.stderr


def test_a_guard_that_raises_an_unexpected_error_still_denies(
    adapter: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def crash(*_: object) -> int:
        raise KeyError("rule")

    monkeypatch.setattr(adapter.ADAPTER, "_payload", dict)
    monkeypatch.setattr(adapter.ADAPTER, "dispatch", crash)
    assert adapter.ADAPTER.main(["shell", "git"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["decision"] == "deny"
    assert "KeyError" in captured.err


def test_an_allow_with_a_notice_prints_only_the_pass_through(
    adapter: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    hook_decision = adapter.provider_adapter.hook_decision
    assert adapter.ADAPTER._emit(hook_decision.Verdict("allow", notice="once")) == 0
    assert capsys.readouterr().out == ""


def test_session_start_without_cwd_uses_the_first_workspace(adapter: ModuleType) -> None:
    payload = {
        "conversationId": CONVERSATION,
        "workspacePaths": ["/work/a", "/work/b"],
        "hookEventName": "SessionStart",
    }
    assert adapter.read(payload)["cwd"] == "/work/a"


@pytest.mark.parametrize("paths", [None, [], "/work", [1]])
def test_a_malformed_workspace_list_gives_no_cwd(adapter: ModuleType, paths: object) -> None:
    assert adapter.read({"workspacePaths": paths})["cwd"] == ""


def test_session_start_registers_from_workspace_paths_alone(run_cli: CliRunner, project: Path) -> None:
    payload = {"conversationId": CONVERSATION, "workspacePaths": [str(project)], "hookEventName": "SessionStart"}
    result = run_cli(SCRIPT, "native", "session-start", payload=payload)
    assert result.returncode == 0
    assert "injectSteps" in stdout_object(result)


@pytest.mark.parametrize("chunks", ["text", [1], [{"ReplacementContent": 1}], [{}], {"ReplacementContent": "x"}])
def test_malformed_replacement_chunks_are_denied(run_cli: CliRunner, project: Path, chunks: object) -> None:
    args = {"TargetFile": "src/a.py", "ReplacementChunks": chunks}
    result = run_cli(SCRIPT, "content", "write", payload=tool_payload(project, "multi_replace_file_content", args))
    assert stdout_object(result)["decision"] == "deny"
    assert "malformed" in stdout_object(result)["reason"]
