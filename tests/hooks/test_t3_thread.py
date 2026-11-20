"""T3 lanes start only on Claude or Codex, in forms the guard can read, and run outside the sandbox."""

import json

import pytest
from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")
START = "t3 thread start --provider claudeAgent --model opus --worktree origin/main --branch feat/x --title lane-a"


def verdict(command: str) -> str:
    """The combined decision of the forbidden and allowed guards, as a provider merges them."""
    decisions = {
        guard.decide(kind, {"tool_input": {"command": command}}).decision for kind in ("forbidden", "allowed")
    }
    return next(decision for decision in ("deny", "ask", "allow") if decision in decisions)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"{START} . 'Read /tmp/brief.md and carry out the lane'", id="a Claude lane in a new worktree"),
        pytest.param("t3 thread start --provider codex --model gpt-5.5 --json . hello", id="a Codex thread"),
        pytest.param("t3 thread start . hello --provider=codex --model=gpt-5.5 --wait", id="options after the words"),
        pytest.param("t3 thread send thread-1 'Address the review' --wait --json", id="a message to a thread"),
        pytest.param("t3 thread show thread-1 --messages 3 --json", id="a thread read"),
        pytest.param("t3 thread list --project . --json", id="a thread listing"),
        pytest.param("t3 thread list", id="a plain thread listing"),
    ],
)
def test_lane_forms_run_without_approval(command: str) -> None:
    assert verdict(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("t3 thread start --model opus . hello", id="no provider, so the project default"),
        pytest.param("t3 thread start . hello", id="no provider or model"),
        pytest.param("t3 thread start --provider antigravity --model gemini . hello", id="Antigravity"),
        pytest.param("t3 thread start --provider=antigravity --model=gemini . hello", id="Antigravity with ="),
        pytest.param("t3 thread start --provider my-claude --model opus . hello", id="a user-named instance"),
        pytest.param("t3 thread start --provider ClaudeAgent --model opus . hello", id="a near miss of the id"),
        pytest.param("t3 thread start --provider codex --provider antigravity --model m . hi", id="a second provider"),
        pytest.param("cd /repo && t3 thread start --model opus . hello", id="inside a list"),
        pytest.param("env FOO=1 t3 thread start --model opus . hello", id="behind a wrapper"),
        pytest.param("bash -c 't3 thread start --model opus . hello'", id="inside a shell script"),
        pytest.param("/nix/store/x-t3/bin/t3 thread start . hello", id="invoked by path"),
        pytest.param("t3 --log-level info thread start . hello", id="behind a global option"),
    ],
)
def test_a_thread_on_a_provider_other_than_claude_or_codex_is_refused(command: str) -> None:
    result = guard.decide("forbidden", {"tool_input": {"command": command}})
    assert result.decision == "deny"
    assert "claudeAgent" in result.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "t3 thread start --provider codex --model m --base-dir /tmp/t3 . hi", id="another data directory"
        ),
        pytest.param("T3CODE_HOME=/tmp/t3 t3 thread start --provider codex --model m . hi", id="a data directory env"),
        pytest.param("t3 thread start --provider codex . hi", id="a provider without a model"),
        pytest.param("t3 thread start --provider codex --model m --wizard . hi", id="an unknown option"),
        pytest.param("t3 thread start --provider codex --model m . hi extra", id="an extra word"),
        pytest.param("t3 thread start --provider codex --model m --title --json . hi", id="an option as a value"),
        pytest.param("t3 thread start --provider codex --model m -- . hi", id="an end of options"),
        pytest.param('t3 thread start --provider "$P" --model m . hi', id="a run-time provider"),
        pytest.param("t3 thread start --provider codex --model m $ARGS . hi", id="words split at run time"),
        pytest.param("env t3 thread start --provider codex --model m . hi", id="behind a wrapper"),
        pytest.param("t3 thread send thread-1 hi --base-dir /tmp/t3", id="a send to another data directory"),
        pytest.param("t3 thread send thread-1", id="a send without a message"),
        pytest.param("t3 thread show thread-1 --base-dir /tmp/t3", id="a read of another data directory"),
        pytest.param(
            't3 thread start --provider codex --model m . "$(cp /etc/passwd /tmp/leak; echo hi)"',
            id="a substitution the unsandboxed shell would run",
        ),
        pytest.param('t3 thread send "$THREAD" hi', id="a run-time thread"),
        pytest.param("t3 thread show thread-1 --messages ~/n", id="a tilde"),
        pytest.param("t3 thread start --provider codex --model m . - <<EOF\n$(id)\nEOF", id="an expanding heredoc"),
        pytest.param("cp /etc/passwd /tmp/leak; t3 thread list", id="a list the unsandboxed shell would run"),
        pytest.param(
            "t3 thread start --provider codex --model m . - < ~/.ssh/id_ed25519", id="a message from any file"
        ),
        pytest.param("t3 thread start --provider codex --model m . - <<'EOF'\nbrief\nEOF", id="a message from stdin"),
        pytest.param("t3 thread archive thread-1", id="an unknown thread subcommand"),
    ],
)
def test_forms_the_guard_cannot_read_need_review(command: str) -> None:
    assert verdict(command) == "ask"


@pytest.mark.parametrize(
    "command",
    ["echo t3 thread start . hello", "git commit -m 't3 thread start . hello'", "t3 service status"],
    ids=["an echo", "a commit message", "another t3 subcommand"],
)
def test_text_and_other_t3_subcommands_are_not_judged_as_a_thread_start(command: str) -> None:
    assert guard.decide("forbidden", {"tool_input": {"command": command}}).decision == "allow"


def test_thread_commands_leave_the_claude_sandbox() -> None:
    sandbox = json.loads((REPO_ROOT / "agents/claude/settings.json").read_text())["sandbox"]
    assert "t3 thread *" in sandbox["excludedCommands"]
    assert [command for command in sandbox["excludedCommands"] if command.startswith("t3 ")] == ["t3 thread *"]


def test_only_thread_commands_have_shared_permission_prefixes() -> None:
    rules = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
    t3 = {(rule["decision"], tuple(rule["prefix"])) for rule in rules if rule["prefix"][0] == "t3"}
    assert t3 == {("allow", ("t3", "thread", action)) for action in ("start", "send", "show", "list")}
