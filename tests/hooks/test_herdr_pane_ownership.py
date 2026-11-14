"""A session may type into the panes of agents it started; any other pane may run outside the sandbox."""

from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import decision, run, set_agents, start_agent
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")

OWNED_PANE_COMMANDS = [
    "herdr pane send-text p1 'continue with the next slice'",
    "herdr pane send-keys p1 Enter",
    "herdr pane run p1 '/compact'",
    "herdr agent send-keys lane-a esc",
]


@pytest.mark.parametrize("command", OWNED_PANE_COMMANDS)
def test_a_session_drives_the_pane_of_an_agent_it_started(repository: Path, herdr: Path, command: str) -> None:
    start_agent(repository, herdr, "w1")
    assert decision(run(repository, command)) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "herdr pane send-text w1:p9 'rm -rf ~'",
        "herdr pane send-keys w1:p9 Enter",
        "herdr pane run w1:p9 'rm -rf ~'",
        "herdr agent send-keys reviewer Enter",
        "herdr pane run $PANE 'rm -rf ~'",
        "herdr agent send-keys $AGENT Enter",
    ],
    ids=["text", "keys", "run", "agent keys", "run-time pane", "run-time agent"],
)
def test_driving_a_pane_the_session_did_not_start_asks(repository: Path, herdr: Path, command: str) -> None:
    start_agent(repository, herdr, "w1")
    output = run(repository, command)
    assert decision(output) == "ask"
    assert "not started by this session" in output["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("command", OWNED_PANE_COMMANDS)
def test_a_pane_whose_agent_exited_is_no_longer_owned(repository: Path, herdr: Path, command: str) -> None:
    start_agent(repository, herdr, "w1")
    set_agents(herdr, "")
    assert decision(run(repository, command)) == "ask"


@pytest.mark.parametrize("command", OWNED_PANE_COMMANDS)
def test_a_pane_another_agent_took_over_is_no_longer_owned(repository: Path, herdr: Path, command: str) -> None:
    start_agent(repository, herdr, "w1")
    set_agents(herdr, "lane-a w1 term_replacement session_agent\n")
    assert decision(run(repository, command)) == "ask"


@pytest.mark.parametrize("form", ["{}; echo done", "{} | cat", "env HERDR_SOCKET_PATH=/tmp/other.sock {}"])
@pytest.mark.parametrize("command", OWNED_PANE_COMMANDS)
def test_driving_an_owned_pane_needs_one_simple_direct_call(
    repository: Path, herdr: Path, command: str, form: str
) -> None:
    start_agent(repository, herdr, "w1")
    assert decision(run(repository, form.format(command))) == "ask"


@pytest.mark.usefixtures("isolated_project")
@pytest.mark.parametrize("command", OWNED_PANE_COMMANDS)
def test_the_command_guard_lists_the_pane_driving_forms(command: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "herdr --session other pane run p1 'echo hi'",
        "herdr pane run p1",
        "herdr pane send-text --raw p1 hello",
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_the_command_guard_asks_for_other_pane_driving_forms(command: str) -> None:
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
