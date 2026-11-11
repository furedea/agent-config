"""Stop-time model rules: what the Stop message tells about the time spent and the work the cap left out."""

import re
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools
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
    tools.write_report([])

    assert re.search(r"judged 1 of 1 subject\(s\) in \d+\.\ds", stop(record)["systemMessage"])


def test_the_message_tells_how_many_judged_subjects_came_from_the_verdict_cache(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(10, [("a.py", 10)], cached=4)

    assert "4 cached" in stop(record)["reason"]


def test_the_cap_counts_only_the_cached_subjects_of_the_files_it_kept(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES, cached=5)
    tools.write_plan_of_files(("a.py", "c.py"), subjects=20, cached=3)

    assert "3 cached" in stop(record)["reason"]


def test_the_message_counts_no_cached_subject_when_the_plan_has_none(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(10, [("a.py", 10)])

    assert "0 cached" in stop(record)["reason"]


def test_the_message_tells_the_subjects_and_files_the_cap_skipped(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)

    assert "15 subject(s) in 1 file(s) skipped by the cap of 20" in stop(record)["reason"]


def test_a_receipt_for_unchanged_inputs_is_reused_even_when_the_cap_skipped_subjects(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    stop(record, active=True)

    again = stop(record, active=True)

    assert "unchanged; not rerun" in again["systemMessage"]
    assert len(tools.calls("op")) == 1
