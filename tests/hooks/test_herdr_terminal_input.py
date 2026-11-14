"""Typing into any pane stays with the user; Herdr help runs without approval."""

import json
from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import decision, run
from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
POLICY = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
TERMINAL_INPUTS = [
    ("herdr", "pane", "send-text"),
    ("herdr", "pane", "send-keys"),
    ("herdr", "pane", "run"),
    ("herdr", "agent", "send-keys"),
]


@pytest.mark.parametrize("prefix", TERMINAL_INPUTS)
def test_raw_terminal_input_asks_even_for_a_pane_the_session_started(prefix: tuple[str, ...]) -> None:
    """Keys or text can answer the agent's approval prompt or end it and reach the shell beneath it."""
    decisions = {rule["decision"] for rule in POLICY if tuple(rule["prefix"]) == prefix}
    assert decisions == {"ask"}


@pytest.mark.usefixtures("isolated_project")
@pytest.mark.parametrize(
    "command",
    [
        "nohup herdr pane send-keys p1 Enter",
        "timeout 5 herdr pane run p1 '/compact'",
        "command herdr agent send-keys lane-a Down Enter",
    ],
)
def test_terminal_input_behind_a_wrapper_asks_in_the_command_guard(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"


@pytest.mark.usefixtures("isolated_project")
@pytest.mark.parametrize(
    "command", ["herdr worktree create --help", "herdr pane send-text --help", "herdr pane --help"]
)
def test_herdr_help_runs_unprompted(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.usefixtures("isolated_project")
@pytest.mark.parametrize("command", ["herdr worktree create --help --path /tmp/x", "herdr --session x pane --help"])
def test_herdr_help_with_other_words_is_judged_by_its_own_form(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "ask"


@pytest.mark.parametrize("command", ["herdr agent prompt --help", "herdr agent start --help"])
@pytest.mark.usefixtures("herdr")
def test_help_for_an_ownership_action_is_not_an_ownership_action(repository: Path, command: str) -> None:
    assert decision(run(repository, command)) == "allow"
