"""A session may message, end, or remove only the hc terminals it started; any other may be the user's."""

import json
import os
from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import after, decision, open_lane, run
from tests.runtime import REPO_ROOT

pytestmark = pytest.mark.usefixtures("core")
START = "hc run --bg --no-parent --json --name lane-a claude 'Read /tmp/brief.md'"
CREATED_MS = 1795000000000


def launched(address: str, created_ms: object = CREATED_MS) -> dict:
    """What a Bash tool reports for `hc run --bg --json`: the started terminal on stdout."""
    terminal = {"address": address, "name": "lane-a", "created_ms": created_ms, "state": "live"}
    return {"stdout": json.dumps(terminal) + "\n"}


def serve(core: Path, address: str, created_ms: int = CREATED_MS) -> None:
    """What `hc get <address> --json` prints for the terminal the core now holds at that address."""
    (core / f"get-{address}.json").write_text(json.dumps({"address": address, "created_ms": created_ms}))


@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The live terminals `hc get` reports come from files the test controls; t7 is the one this session starts."""
    directory = tmp_path / "hc-bin"
    directory.mkdir()
    (directory / "hc").symlink_to(Path(__file__).with_name("fake_hc.sh"))
    monkeypatch.setenv("HC_TEST_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ['PATH']}")
    serve(tmp_path, "t7")
    return tmp_path


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
        pytest.param(START, launched("t7", created_ms=None), id="no creation time"),
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


@pytest.mark.parametrize("action", ["send t7 hi", "kill t7", "rm t7"])
def test_an_address_the_core_now_gives_another_terminal_asks(repository: Path, core: Path, action: str) -> None:
    start_terminal(repository)
    serve(core, "t7", created_ms=CREATED_MS + 1)
    output = run(repository, f"hc {action}")
    assert decision(output) == "ask"
    assert "another terminal" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_core_that_cannot_answer_cannot_vouch_for_an_address(repository: Path, core: Path) -> None:
    start_terminal(repository)
    (core / "get-t7.json").unlink()
    assert decision(run(repository, "hc send t7 hi")) == "ask"


@pytest.mark.parametrize("directory", [".", "src", "src/../docs"])
def test_a_lane_may_start_inside_this_sessions_checkout(repository: Path, directory: str) -> None:
    command = START.replace("--name lane-a", f"--name lane-a --cwd {(repository / directory).absolute()}")
    assert decision(run(repository, command)) == "allow"


@pytest.mark.usefixtures("herdr")
def test_a_lane_may_start_in_a_worktree_this_session_created(repository: Path, tmp_path: Path) -> None:
    open_lane(repository, tmp_path)
    assert decision(run(repository, START.replace("--name lane-a", "--name lane-a --cwd /lanes/w6"))) == "allow"


@pytest.mark.parametrize(
    "directory",
    ["/home/user", "/lanes/w6", "src", "{repository}/../other", "{repository}-other"],
    ids=["a home", "a worktree another session created", "a relative path", "a parent escape", "a sibling prefix"],
)
def test_a_lane_rooted_outside_this_sessions_checkouts_asks(repository: Path, directory: str) -> None:
    command = START.replace("--name lane-a", f"--name lane-a --cwd {directory.format(repository=repository)}")
    output = run(repository, command)
    assert decision(output) == "ask"
    assert "outside" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_claude_start_reaches_the_ownership_record() -> None:
    settings = json.loads((REPO_ROOT / "agents/hooks.json").read_text())
    filters = {
        hook.get("if")
        for group in settings["claude"]["PostToolUse"]
        for hook in group["hooks"]
        if "verification_session.py" in hook["command"]
    }
    assert "Bash(hc run *)" in filters
