"""Provider settings preserve the native hook contracts after rendering."""

import json
from pathlib import Path

import pytest

from tests.runtime import CliRunner, load_script_module

pytestmark = pytest.mark.integration


def test_generated_claude_lint_hook_uses_the_dispatcher_without_if(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    agent_harness("generate-claude-settings", "--output", str(path))
    settings = json.loads(path.read_text())
    groups = [group for group in settings["hooks"]["PostToolUse"] if group.get("matcher") == "Write|Edit|NotebookEdit"]
    lint_hooks = [hook for group in groups for hook in group["hooks"] if "lint_format.py" in hook["command"]]
    assert len(lint_hooks) == 1
    assert lint_hooks[0]["command"].endswith('lint_format.py"')
    assert "if" not in lint_hooks[0]


@pytest.mark.parametrize(
    "matcher,mode",
    [("Write|Edit|NotebookEdit", "harness"), ("Write|Edit|NotebookEdit", "write"), ("Read|Grep", "read")],
)
def test_generated_claude_file_guards_cover_every_file_tool(
    agent_harness: CliRunner, tmp_path: Path, matcher: str, mode: str
) -> None:
    path = tmp_path / "settings.json"
    agent_harness("generate-claude-settings", "--output", str(path))
    groups = [
        group for group in json.loads(path.read_text())["hooks"]["PreToolUse"] if group.get("matcher") == matcher
    ]
    commands = [hook["command"] for group in groups for hook in group["hooks"]]
    assert any(command.endswith(f'guard_file.py" {mode}') for command in commands)


def test_generated_codex_lint_hook_matches_native_apply_patch_aliases(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-codex-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]["PostToolUse"]
    groups = [group for group in hooks if group.get("matcher") == "^apply_patch$|^Edit$|^Write$"]
    lint_hooks = [hook for group in groups for hook in group["hooks"] if 'hook_adapter.py" lint' in hook["command"]]
    assert len(lint_hooks) == 1


def test_generated_devin_hooks_use_only_supported_events_and_native_tools(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "config.json"
    agent_harness("generate-devin-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]
    supported = {
        "PreToolUse",
        "PostToolUse",
        "PermissionRequest",
        "UserPromptSubmit",
        "Stop",
        "PostCompaction",
        "SessionStart",
        "SessionEnd",
    }
    assert set(hooks) <= supported
    assert "PreToolUse" in hooks
    commands = [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]
    assert any('hook_adapter.py" native session-start' in command for command in commands)
    assert any('hook_adapter.py" shell forbidden' in command for command in commands)
    matchers = [group.get("matcher", "") for event in ("PreToolUse", "PostToolUse") for group in hooks.get(event, [])]
    assert any("exec" in matcher for matcher in matchers)
    assert not any("Bash" in matcher for matcher in matchers)


def test_generated_devin_edit_matchers_cover_every_canonical_edit_tool(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "config.json"
    agent_harness("generate-devin-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]
    matchers = [group.get("matcher", "") for event in ("PreToolUse", "PostToolUse") for group in hooks.get(event, [])]
    for tool in ("write", "edit", "multi_edit", "notebook_edit"):
        assert any(tool in matcher for matcher in matchers), tool


def test_generated_hermes_hooks_use_only_supported_events_and_native_tools(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-hermes-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]
    supported = {
        "on_session_start",
        "on_session_end",
        "pre_tool_call",
        "post_tool_call",
        "pre_verify",
    }
    assert set(hooks) <= supported
    assert "pre_tool_call" in hooks
    commands = [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]
    assert any('hook_adapter.py" native session-start' in command for command in commands)
    assert any('hook_adapter.py" native session-end' in command for command in commands)
    assert any('hook_adapter.py" native stop' in command for command in commands)
    assert any('hook_adapter.py" native pre-tool-use' in command for command in commands)
    assert any('hook_adapter.py" shell forbidden' in command for command in commands)
    assert any('hook_adapter.py" content write' in command for command in commands)
    matchers = [
        group.get("matcher", "") for event in ("pre_tool_call", "post_tool_call") for group in hooks.get(event, [])
    ]
    assert any("terminal" in matcher for matcher in matchers)
    assert not any("Bash" in matcher for matcher in matchers)


def test_generated_pi_hooks_use_only_supported_events_and_native_tools(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-pi-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]
    supported = {
        "session_start",
        "session_shutdown",
        "tool_call",
        "tool_result",
        "input",
        "session_before_compact",
        "session_compact",
    }
    assert set(hooks) <= supported
    assert "tool_call" in hooks
    assert "input" in hooks
    commands = [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]
    assert any('hook_adapter.py" native session-start' in command for command in commands)
    assert any('hook_adapter.py" native session-end' in command for command in commands)
    assert any('hook_adapter.py" native pre-tool-use' in command for command in commands)
    assert any('hook_adapter.py" audit compaction' in command for command in commands)
    assert any('hook_adapter.py" shell forbidden' in command for command in commands)
    assert any('hook_adapter.py" content prompt' in command for command in commands)
    matchers = [group.get("matcher", "") for event in ("tool_call", "tool_result") for group in hooks.get(event, [])]
    assert any("bash" in matcher for matcher in matchers)
    assert not any("Bash" in matcher for matcher in matchers)


def test_generated_dsh_hooks_use_only_supported_events_and_native_tools(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-dsh-hooks", "--output", str(path))
    hooks = json.loads(path.read_text())["hooks"]
    assert set(hooks) == {"tools/pre-execute", "tools/post-execute"}
    commands = [hook["command"] for groups in hooks.values() for group in groups for hook in group["hooks"]]
    assert any('hook_adapter.py" shell forbidden' in command for command in commands)
    assert any('hook_adapter.py" paths patch' in command for command in commands)
    assert any('hook_adapter.py" lint' in command for command in commands)
    assert not any('hook_adapter.py" native' in command for command in commands)
    post_matchers = [group.get("matcher", "") for group in hooks["tools/post-execute"]]
    assert any("edit" in matcher for matcher in post_matchers)
    matchers = [group.get("matcher", "") for groups in hooks.values() for group in groups]
    assert any("bash" in matcher for matcher in matchers)
    assert not any("Bash" in matcher for matcher in matchers)


def test_generated_dsh_read_guard_covers_every_file_reading_tool(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-dsh-hooks", "--output", str(path))
    groups = json.loads(path.read_text())["hooks"]["tools/pre-execute"]
    guarded = [
        group.get("matcher", "")
        for group in groups
        if any('hook_adapter.py" content read' in hook["command"] for hook in group["hooks"])
    ]
    for tool in ("read", "read_image", "grep", "str_replace_editor"):
        assert any(tool in matcher for matcher in guarded), tool


@pytest.mark.parametrize("tool", ["write", "edit", "str_replace_editor", "apply_patch"])
@pytest.mark.parametrize("event", ["tools/pre-execute", "tools/post-execute"])
def test_generated_dsh_edit_matchers_cover_every_edit_tool(
    agent_harness: CliRunner, tmp_path: Path, tool: str, event: str
) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-dsh-hooks", "--output", str(path))
    matchers = [group.get("matcher", "") for group in json.loads(path.read_text())["hooks"][event]]
    assert any(tool in matcher for matcher in matchers)


def test_generated_claude_settings_allow_no_unused_notification_host(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    agent_harness("generate-claude-settings", "--output", str(path))
    assert "api.day.app" not in json.loads(path.read_text())["sandbox"]["network"]["allowedDomains"]


def generated_antigravity_hooks(agent_harness: CliRunner, tmp_path: Path) -> dict:
    path = tmp_path / "hooks.json"
    agent_harness("generate-hooks", "--provider", "antigravity", "--output", str(path))
    return json.loads(path.read_text())["hooks"]


def test_generated_antigravity_hooks_use_only_supported_events(agent_harness: CliRunner, tmp_path: Path) -> None:
    hooks = generated_antigravity_hooks(agent_harness, tmp_path)
    assert set(hooks) == {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}


def antigravity_commands(group: dict) -> list[str]:
    return [hook["command"].split('hook_adapter.py" ')[1] for hook in group["hooks"]]


@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse"])
def test_generated_antigravity_tool_hooks_match_every_tool(
    agent_harness: CliRunner, tmp_path: Path, event: str
) -> None:
    groups = generated_antigravity_hooks(agent_harness, tmp_path)[event]
    assert [group for group in groups if group["matcher"] == "*"]


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_generated_antigravity_session_events_list_handlers_directly(
    agent_harness: CliRunner, tmp_path: Path, event: str
) -> None:
    handlers = generated_antigravity_hooks(agent_harness, tmp_path)[event]
    assert handlers
    assert all("command" in handler and "hooks" not in handler for handler in handlers)


def test_generated_antigravity_pre_tool_use_runs_every_guard_on_every_tool(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    groups = generated_antigravity_hooks(agent_harness, tmp_path)["PreToolUse"]
    commands = [command for group in groups if group["matcher"] == "*" for command in antigravity_commands(group)]
    for guard in (
        "native pre-tool-use",
        "audit tool",
        "paths command",
        "paths patch",
        "shell forbidden",
        "shell commit",
        "shell git",
        "shell allowed",
        "harness",
        "content write",
        "content suppression",
    ):
        assert guard in commands


def test_generated_antigravity_content_read_guard_runs_only_for_read_tools(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    groups = generated_antigravity_hooks(agent_harness, tmp_path)["PreToolUse"]
    scoped = [group for group in groups if "content read" in antigravity_commands(group)]
    assert [group["matcher"] for group in scoped] == ["^(read_file|view_file)$"]


def test_generated_antigravity_lint_runs_only_after_edit_tools(agent_harness: CliRunner, tmp_path: Path) -> None:
    groups = generated_antigravity_hooks(agent_harness, tmp_path)["PostToolUse"]
    scoped = [group for group in groups if "lint" in antigravity_commands(group)]
    assert len(scoped) == 1
    for tool in ("write_file", "write_to_file", "edit_file", "replace_file_content", "multi_replace_file_content"):
        assert tool in scoped[0]["matcher"]
    assert "run_command" not in scoped[0]["matcher"]


def test_generated_antigravity_commands_run_the_deployed_adapter_with_arguments_it_accepts(
    agent_harness: CliRunner, tmp_path: Path
) -> None:
    adapter = load_script_module("agents/antigravity/hooks/hook_adapter.py", "antigravity_adapter_wiring").ADAPTER
    hooks = generated_antigravity_hooks(agent_harness, tmp_path)
    handlers = [
        handler
        for event, entries in hooks.items()
        for entry in entries
        for handler in (entry["hooks"] if event.endswith("ToolUse") else [entry])
    ]
    commands = [handler["command"] for handler in handlers]
    prefix = '"$HOME/.gemini/config/hooks/hook_adapter.py" '
    assert commands
    for command in commands:
        assert command.startswith(prefix), command
        kind, *rest = command.removeprefix(prefix).split()
        assert adapter._accepts(kind, rest), command
