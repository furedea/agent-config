"""Stop-time model rules: the time a review took, and how a Stop resumes the subjects the cap skipped."""

import re
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, finding
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import session_store

THREE_FILES = [("a.py", 12), ("b.py", 15), ("c.py", 8)]


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session in a repository of a trusted owner, after one edit."""
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


def test_the_message_tells_the_seconds_spent_and_the_subjects_judged(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)

    reason = stop(record)["reason"]

    assert "judged 20 of 35 subject(s) in " in reason
    assert re.search(r"in \d+\.\ds", reason)


def test_a_clean_review_also_tells_the_seconds_spent(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.report([])

    assert re.search(r"judged 1 of 1 subject\(s\) in \d+\.\ds", stop(record)["systemMessage"])


def test_the_next_stop_on_the_same_inputs_judges_the_files_the_cap_skipped_first(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    first = stop(record)

    second = stop(record, active=True)

    first_launch, second_launch = tools.calls("op")
    assert first_launch["argv"][-2:] == ["a.py", "c.py"]
    assert second_launch["argv"][-3:] == ["a.py", "c.py", "b.py"]
    assert "judged at the next Stop" in first["reason"]
    assert "skipped by the cap" not in second["systemMessage"]


def test_the_resumed_stop_keeps_the_files_judged_before_so_their_findings_are_not_lost(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    stop(record, active=True)

    stop(record, active=True)

    _, resumed = tools.calls("op")
    assert set(resumed["argv"][-3:]) == {"a.py", "b.py", "c.py"}


def test_a_resumed_stop_blocks_only_for_findings_the_agent_has_not_seen(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    tools.report([finding(file="a.py")])
    first = stop(record)
    tools.report([finding(file="a.py"), finding(file="b.py", line=7)])

    second = stop(record)

    assert first["decision"] == "block"
    assert second["decision"] == "block"
    assert "b.py:7" in second["reason"]


def test_a_resumed_stop_with_only_known_findings_only_notifies(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    stop(record)

    second = stop(record)

    assert "decision" not in second
    assert "command-query-naming" in second["systemMessage"]


def test_once_nothing_is_skipped_the_receipt_is_reused(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.plan(35, THREE_FILES)
    stop(record)
    tools.plan(1, [("a.py", 1)])
    stop(record)

    again = stop(record)

    assert "unchanged; not rerun" in again["systemMessage"]
    assert len(tools.calls("op")) == 2


def test_a_file_larger_than_the_cap_is_reported_but_never_makes_the_stop_resume(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(45, [("huge.py", 40), ("a.py", 5)])
    stop(record)

    again = stop(record)

    assert len(tools.calls("op")) == 1
    assert "unchanged; not rerun" in again["systemMessage"]


def test_a_resumed_stop_never_sends_a_file_larger_than_the_cap_that_was_not_judged_before(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(75, [("huge.py", 40), *THREE_FILES])
    stop(record, active=True)

    stop(record, active=True)

    first, resumed = tools.calls("op")
    assert "huge.py" not in first["argv"]
    assert "huge.py" not in resumed["argv"]
    assert resumed["argv"][-3:] == ["a.py", "c.py", "b.py"]


def test_a_stop_that_cannot_resume_keeps_the_unseen_findings_for_the_agent(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    stop(record, active=True)
    tools.behave(exit=3)

    result = stop(record)

    assert result["decision"] == "block"
    assert "command-query-naming" in result["reason"]
    assert "exited with status 3" in result["reason"]
