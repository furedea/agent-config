"""A session may message only the T3 threads it started; any other thread may be the user's or the parent's."""

import json
from pathlib import Path

import pytest
from tests.hooks.herdr_runtime import after, decision, run
from tests.runtime import REPO_ROOT

START = "t3 thread start --provider codex --model gpt-5.5 --json . 'Read /tmp/brief.md'"


def launched(thread: str) -> dict:
    """What a Bash tool reports for `t3 thread start --json`: the server's launch result on stdout."""
    return {"stdout": json.dumps({"threadId": thread, "projectId": "project-1", "runId": "run-1"}) + "\n"}


def start_thread(repository: Path, thread: str = "thread-1", command: str = START) -> None:
    assert decision(run(repository, command)) == "allow"
    after(repository, command, launched(thread))


def test_a_session_messages_the_thread_it_started(repository: Path) -> None:
    start_thread(repository)
    assert decision(run(repository, "t3 thread send thread-1 'Address the review' --wait")) == "allow"


def test_a_thread_id_is_matched_as_t3_reads_it(repository: Path) -> None:
    start_thread(repository)
    assert decision(run(repository, "t3 thread send ' thread-1 ' hi")) == "allow"


def test_a_waited_start_records_the_thread_from_its_run_result(repository: Path) -> None:
    command = START.replace("--json", "--json --wait")
    result = {"threadId": "thread-2", "runId": "run-1", "status": "completed", "reply": "thread-9", "error": None}
    after(repository, command, {"stdout": json.dumps(result)})
    assert decision(run(repository, "t3 thread send thread-2 hi")) == "allow"
    assert decision(run(repository, "t3 thread send thread-9 hi")) == "ask"


@pytest.mark.parametrize(
    "target", ["thread-other", "$THREAD", "thread-1x"], ids=["another thread", "a run-time target", "a longer id"]
)
def test_messaging_a_thread_the_session_did_not_start_asks(repository: Path, target: str) -> None:
    start_thread(repository)
    output = run(repository, f"t3 thread send {target} 'rm -rf ~'")
    assert decision(output) == "ask"
    assert "not started by this session" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_every_send_in_a_command_must_target_an_owned_thread(repository: Path) -> None:
    start_thread(repository)
    assert decision(run(repository, "t3 thread send thread-1 a && t3 thread send thread-other b")) == "ask"
    assert decision(run(repository, "env t3 thread send thread-other b")) == "ask"


def test_ownership_belongs_to_one_session(repository: Path) -> None:
    start_thread(repository)
    assert decision(run(repository, "t3 thread send thread-1 hi", session="other")) != "allow"


@pytest.mark.parametrize(
    ("command", "response"),
    [
        pytest.param(START.replace(" --json", ""), {"stdout": "thread-1\n"}, id="plain output a reply could forge"),
        pytest.param(START + "; echo done", launched("thread-1"), id="a list whose output another command shares"),
        pytest.param(START + " | cat", launched("thread-1"), id="a pipeline"),
        pytest.param("env " + START, launched("thread-1"), id="behind a wrapper"),
        pytest.param("./" + START, launched("thread-1"), id="a program by path that may print anything"),
        pytest.param("T3CODE_HOME=/tmp/t3 " + START, launched("thread-1"), id="another data directory"),
        pytest.param(START.replace("'Read /tmp/brief.md'", '"$(cat brief)"'), launched("thread-1"), id="run-time"),
        pytest.param("t3 thread list --json", launched("thread-1"), id="a listing"),
        pytest.param(START, {"stdout": launched("thread-1")["stdout"], "interrupted": True}, id="an interrupted run"),
        pytest.param(START, {"stdout": "not json"}, id="malformed output"),
        pytest.param(START, {"stdout": json.dumps({"threadId": ""})}, id="an empty id"),
    ],
)
def test_only_the_launch_result_of_one_plain_start_records_a_thread(
    repository: Path, command: str, response: dict
) -> None:
    after(repository, command, response)
    assert decision(run(repository, "t3 thread send thread-1 hi")) == "ask"


@pytest.mark.parametrize(
    "command",
    ["t3 thread show thread-other --json", "t3 thread list --json", START, "echo t3 thread send thread-other hi"],
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
    assert "Bash(t3 thread start *)" in filters
