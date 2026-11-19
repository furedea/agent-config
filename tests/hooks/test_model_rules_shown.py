"""Stop-time model rules show a finding once per session, identified by its rule and its subject's text."""

import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, finding
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_gate
import session_store

SUBJECT = "def first():\n    return 1\n"


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, SUBJECT + "other = 1\n")
    return registered


def spanning(rule: str = "command-query-naming", line: int = 1) -> dict:
    return {**finding(rule=rule, line=line), "endLine": line + 1, "ruleKey": f"python/{rule}"}


def test_a_finding_shown_once_is_not_shown_again_after_an_unrelated_edit(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([spanning()])
    stop(record)
    edit(record, SUBJECT + "other = 2\n")

    again = stop(record)

    assert "decision" not in again
    assert "0 findings · 1 already shown" in again["systemMessage"]


def test_a_subject_that_only_moved_stays_hidden(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.write_report([spanning()])
    stop(record)
    edit(record, "# new header\n" + SUBJECT + "other = 1\n")
    tools.write_report([spanning(line=2)])

    assert "decision" not in stop(record)


def test_a_subject_whose_body_changed_is_shown_again(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.write_report([spanning()])
    stop(record)
    edit(record, "def first():\n    return 2\nother = 1\n")

    assert stop(record)["decision"] == "block"


def test_only_the_new_findings_are_listed_and_the_old_ones_counted(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([spanning()])
    stop(record)
    edit(record, SUBJECT + "other = 2\n")
    tools.write_report([spanning(), spanning(rule="other-rule", line=3)])

    result = stop(record)

    assert result["decision"] == "block"
    assert "other-rule" in result["reason"]
    assert "command-query-naming" not in result["reason"]
    assert "1 finding · 1 already shown" in result["reason"]


def test_a_new_session_shows_the_finding_again(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.write_report([spanning()])
    stop(record)
    later = session_store.register(record.root, "claude", "another-session")
    edit(later, SUBJECT + "other = 3\n")

    assert stop(later)["decision"] == "block"


def test_findings_with_identical_subjects_are_all_listed_and_later_all_hidden(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    edit(record, "x = 1\nx = 1\n")
    tools.write_report([finding(line=1), finding(line=2)])

    first = stop(record)
    edit(record, "x = 1\nx = 1\ny = 2\n")
    second = stop(record)

    assert first["reason"].count("command-query-naming") == 2
    assert "decision" not in second
    assert "2 already shown" in second["systemMessage"]


def test_findings_are_not_remembered_when_saving_the_receipt_fails(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools.write_report([spanning()])
    save = session_store.SessionRecord.save_results

    def failing_for_model_rules(self: session_store.SessionRecord, value: dict) -> None:
        if model_rules_gate.RECEIPT_KEY in value:
            raise OSError("disk full")
        save(self, value)

    with monkeypatch.context() as patch:
        patch.setattr(session_store.SessionRecord, "save_results", failing_for_model_rules)
        stop(record)
    edit(record, SUBJECT + "other = 2\n")

    assert stop(record)["decision"] == "block"
