"""Stop-time model rules: the time a review took, and how a Stop resumes the subjects the cap skipped."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, finding
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import session_store

# 50 subjects: the cap of 20 admits a.py and c.py, which leaves b.py and d.py (30 subjects) for later Stops.
FOUR_FILES = [("a.py", 12), ("b.py", 15), ("c.py", 8), ("d.py", 15)]
CAP = 20


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session in a repository of a trusted owner, after one edit."""
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


@pytest.fixture
def first_run_skipped_b_and_d(record: session_store.SessionRecord, tools: Tools) -> None:
    """The first Stop on the inputs: it judged a.py and c.py and skipped b.py and d.py; the agent was not shown."""
    tools.plan(50, FOUR_FILES)
    stop(record, active=True)
    tools.plan(50, FOUR_FILES, cached=CAP)


def test_the_message_tells_the_seconds_spent_and_the_subjects_judged(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES)

    reason = stop(record)["reason"]

    assert "judged 20 of 50 subject(s) in " in reason
    assert re.search(r"in \d+\.\ds", reason)


def test_a_clean_review_also_tells_the_seconds_spent(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.report([])

    assert re.search(r"judged 1 of 1 subject\(s\) in \d+\.\ds", stop(record)["systemMessage"])


def test_the_message_says_the_skipped_subjects_are_judged_at_the_next_stop(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES)

    assert "judged at the next Stop" in stop(record)["reason"]


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_the_next_stop_judges_the_files_the_cap_skipped_before_it_sends_the_files_judged_before(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record, active=True)

    first, resumed = tools.calls("op")
    assert first["argv"][-2:] == ["a.py", "c.py"]
    assert resumed["argv"][-3:] == ["a.py", "c.py", "b.py"]


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_the_stop_after_that_judges_what_is_left_and_then_the_receipt_is_final(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record, active=True)
    tools.plan(50, FOUR_FILES, cached=35)

    last = stop(record, active=True)
    again = stop(record, active=True)

    assert "skipped by the cap" not in last["systemMessage"]
    assert "unchanged; not rerun" in again["systemMessage"]
    assert len(tools.calls("op")) == 3


def test_when_what_is_left_fits_the_cap_the_resume_judges_the_whole_diff_from_the_cache(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, [("a.py", 12), ("b.py", 15), ("c.py", 8)])
    stop(record, active=True)
    tools.plan(35, [("a.py", 12), ("b.py", 15), ("c.py", 8)], cached=20)

    second = stop(record, active=True)

    assert "skipped by the cap" not in second["systemMessage"]
    assert "judged 35 of 35" in second["systemMessage"]


def test_a_resumed_stop_blocks_only_for_findings_the_agent_has_not_seen(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES)
    tools.report([finding(file="a.py")])
    first = stop(record)
    tools.plan(50, FOUR_FILES, cached=CAP)
    tools.report([finding(file="a.py"), finding(file="b.py", line=7)])

    second = stop(record)

    assert first["decision"] == "block"
    assert second["decision"] == "block"
    assert "b.py:7" in second["reason"]


def test_a_resumed_stop_with_only_known_findings_only_notifies(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES)
    stop(record)
    tools.plan(50, FOUR_FILES, cached=CAP)

    second = stop(record)

    assert "decision" not in second
    assert "command-query-naming" in second["systemMessage"]


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
    tools.plan(90, [("huge.py", 40), *FOUR_FILES])
    stop(record, active=True)
    tools.plan(90, [("huge.py", 40), *FOUR_FILES], cached=CAP)

    stop(record, active=True)

    first, resumed = tools.calls("op")
    assert "huge.py" not in first["argv"]
    assert "huge.py" not in resumed["argv"]
    assert resumed["argv"][-3:] == ["a.py", "c.py", "b.py"]


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_a_resumed_stop_does_not_resend_the_files_judged_before_when_the_verdict_cache_no_longer_has_them(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES)

    stop(record, active=True)

    _, resumed = tools.calls("op")
    assert resumed["argv"][-1] == "b.py"
    assert "a.py" not in resumed["argv"]
    assert "c.py" not in resumed["argv"]


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_a_resumed_stop_trusts_the_cache_only_when_the_dry_run_matches_what_it_judged(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(50, FOUR_FILES, cached=25)

    stop(record, active=True)

    _, resumed = tools.calls("op")
    assert "a.py" not in resumed["argv"]
    assert "c.py" not in resumed["argv"]


def test_files_judged_before_do_not_use_up_the_cap_the_other_review_needs(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    commit_file(record, "committed.txt")
    tools.plan(45, [("x.py", 25), ("a.py", 20)], for_commits=True)
    tools.plan(5, [("d.py", 5)])
    first = stop(record, active=True)
    tools.plan(45, [("x.py", 25), ("a.py", 20)], cached=20, for_commits=True)

    second = stop(record, active=True)

    uncommitted_calls = [call for call in tools.calls("op") if "--base" not in call["argv"]]
    assert "judged at the next Stop" in first["systemMessage"]
    assert len(uncommitted_calls) == 1
    assert "judged at the next Stop" not in second["systemMessage"]


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_findings_shown_by_a_block_after_a_failed_resume_do_not_block_again_when_the_resume_succeeds(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.behave(exit=3)
    shown = stop(record)
    tools.behave()

    resumed = stop(record)

    assert shown["decision"] == "block"
    assert "decision" not in resumed


@pytest.mark.usefixtures("first_run_skipped_b_and_d")
def test_a_stop_that_cannot_resume_keeps_the_unseen_findings_for_the_agent(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.behave(exit=3)

    result = stop(record)

    assert result["decision"] == "block"
    assert "command-query-naming" in result["reason"]
    assert "exited with status 3" in result["reason"]


def commit_file(record: session_store.SessionRecord, name: str) -> None:
    (record.root / name).write_text("committed\n")
    subprocess.run(["git", "add", name], cwd=record.root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "later"], cwd=record.root, check=True)
