"""A session may message, end, or remove only the hc terminals it started; any other may be the user's."""

import json
from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import after, decision, run
from tests.runtime import REPO_ROOT

START = "hc run --bg --no-parent --json --name lane-a --cwd /wt/lane-a claude 'Read /tmp/brief.md'"


def launched(address: str, name: str = "lane-a") -> dict:
    """What a Bash tool reports for `hc run --bg --json`: the started terminal on stdout."""
    terminal = {"address": address, "name": name, "argv": ["claude", "Read /tmp/brief.md"], "state": "live"}
    return {"stdout": json.dumps(terminal) + "\n"}


def start_terminal(repository: Path, address: str = "t7", command: str = START) -> None:
    assert decision(run(repository, command)) == "allow"
    after(repository, command, launched(address))


@pytest.mark.parametrize("command", ["hc send t7 'Address the review'", "hc kill t7", "hc rm t7"])
def test_a_session_drives_the_terminal_it_started(repository: Path, command: str) -> None:
    start_terminal(repository)
    assert decision(run(repository, command)) == "allow"


@pytest.mark.parametrize(
    "target",
    ["t8", "$TERMINAL", "t77", "lane-a", "box/t7"],
    ids=["another terminal", "a run-time target", "a longer address", "a name a later terminal may reuse", "remote"],
)
@pytest.mark.parametrize("action", ["send {target} 'rm -rf ~'", "kill {target}", "rm {target}"])
def test_driving_a_terminal_the_session_did_not_start_asks(repository: Path, target: str, action: str) -> None:
    start_terminal(repository)
    output = run(repository, "hc " + action.format(target=target))
    assert decision(output) == "ask"
    assert "not started by this session" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_every_send_in_a_command_must_target_an_owned_terminal(repository: Path) -> None:
    start_terminal(repository)
    assert decision(run(repository, "hc send t7 a && hc send t8 b")) == "ask"
    assert decision(run(repository, "env hc send t8 b")) == "ask"


def test_ownership_belongs_to_one_session(repository: Path) -> None:
    start_terminal(repository)
    assert decision(run(repository, "hc send t7 hi", session="other")) != "allow"


@pytest.mark.parametrize(
    ("command", "response"),
    [
        pytest.param(START.replace(" --json", ""), {"stdout": "t7\n"}, id="plain output a program could forge"),
        pytest.param(START + "; echo done", launched("t7"), id="a list whose output another command shares"),
        pytest.param(START + " | cat", launched("t7"), id="a pipeline"),
        pytest.param("env " + START, launched("t7"), id="behind a wrapper"),
        pytest.param("./" + START, launched("t7"), id="a program by path that may print anything"),
        pytest.param("HC_SESSION=/tmp/x " + START, launched("t7"), id="another core"),
        pytest.param(START.replace("'Read /tmp/brief.md'", '"$(cat brief)"'), launched("t7"), id="run-time"),
        pytest.param("hc ls --json", launched("t7"), id="a listing"),
        pytest.param("hc get t7 --json", launched("t7"), id="a read"),
        pytest.param(START, {"stdout": launched("t7")["stdout"], "interrupted": True}, id="an interrupted run"),
        pytest.param(START, {"stdout": "not json"}, id="malformed output"),
        pytest.param(START, {"stdout": json.dumps({"address": ""})}, id="an empty address"),
    ],
)
def test_only_the_result_of_one_plain_start_records_a_terminal(repository: Path, command: str, response: dict) -> None:
    after(repository, command, response)
    assert decision(run(repository, "hc send t7 hi")) == "ask"


@pytest.mark.parametrize(
    "command", ["hc read t8 --lines 50", "hc wait t8 --json", "hc ls --json", START, "echo hc send t8 hi"]
)
def test_reads_starts_and_text_are_not_the_ownership_checks_concern(repository: Path, command: str) -> None:
    assert decision(run(repository, command)) == "allow"


def test_a_claude_start_reaches_the_ownership_record() -> None:
    settings = json.loads((REPO_ROOT / "agents/hooks.json").read_text())
    filters = {
        hook.get("if")
        for group in settings["claude"]["PostToolUse"]
        for hook in group["hooks"]
        if "verification_session.py" in hook["command"]
    }
    assert "Bash(hc run *)" in filters
