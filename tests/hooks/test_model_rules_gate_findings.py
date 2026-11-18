"""Findings of a promoted rule (severity error) are a gate: they block every Stop until the code is fixed.

`jev-lint review --fail-on error` exits 1 when it reports such a finding, so that exit is a result to read, not a
failed run. Findings of the other rules stay advisory and block once, as `test_model_rules` states.
"""

import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, finding
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import session_store

GATE_FINDING = finding(rule="promoted-rule", line=7, severity="error")


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


@pytest.fixture
def gate_finding(tools: Tools) -> None:
    """jev-lint as it reports a finding of a severity-error rule: the finding, and exit status 1."""
    tools.write_report([GATE_FINDING])
    tools.behave(exit=1)


@pytest.mark.usefixtures("gate_finding")
def test_an_error_finding_blocks_with_its_rule_and_location(record: session_store.SessionRecord) -> None:
    result = stop(record)

    assert result["decision"] == "block"
    assert "promoted-rule" in result["reason"]
    assert "notes.txt:7" in result["reason"]


@pytest.mark.usefixtures("gate_finding")
def test_an_error_finding_blocks_again_on_unchanged_inputs_without_asking_the_model_again(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record)
    again = stop(record)

    assert again["decision"] == "block"
    assert "promoted-rule" in again["reason"]
    assert len(tools.calls("op")) == 1


@pytest.mark.usefixtures("gate_finding")
def test_an_error_finding_blocks_even_after_the_agent_continued_because_of_a_stop_block(
    record: session_store.SessionRecord,
) -> None:
    first = stop(record, active=True)
    reused = stop(record, active=True)

    assert first["decision"] == "block"
    assert reused["decision"] == "block"
    assert "promoted-rule" in reused["reason"]


@pytest.mark.usefixtures("gate_finding")
def test_an_error_finding_stops_blocking_once_a_change_clears_it(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record)
    edit(record, "fixed\n")
    tools.write_report([])
    tools.behave(exit=0)

    result = stop(record, active=True)

    assert "decision" not in result
    assert "0 findings" in result["systemMessage"]


def test_advisory_findings_shown_by_a_gate_block_are_not_shown_again_by_the_next_one(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([GATE_FINDING, finding(line=3)])
    tools.behave(exit=1)

    first = stop(record)
    again = stop(record)

    assert "notes.txt:3" in first["reason"]
    assert again["decision"] == "block"
    assert "notes.txt:7" in again["reason"]
    assert "notes.txt:3" not in again["reason"]


def test_exit_status_1_without_an_error_finding_is_a_failed_run_that_does_not_block(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.behave(exit=1)

    result = stop(record)

    assert "decision" not in result
    assert "exited with status 1" in result["systemMessage"]


def test_exit_status_1_with_an_unreadable_report_is_a_failed_run_that_does_not_block(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.raw_report("op: the service account token is not valid")
    tools.behave(exit=1)

    result = stop(record)

    assert "decision" not in result
    assert "exited with status 1" in result["systemMessage"]


def test_the_block_tells_apart_gating_findings_that_block_until_fixed_from_advisory_ones(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([GATE_FINDING, finding(line=3)])
    tools.behave(exit=1)

    reason = stop(record)["reason"]

    assert "· blocking ·" in reason
    assert "· advisory ·" not in reason
    [gating_line] = [line for line in reason.splitlines() if "notes.txt:7" in line]
    [advisory_line] = [line for line in reason.splitlines() if "notes.txt:3" in line]
    assert "until fixed" in gating_line
    assert "until fixed" not in advisory_line


@pytest.mark.usefixtures("gate_finding")
def test_a_block_of_only_gating_findings_does_not_offer_explaining_them_away(
    record: session_store.SessionRecord,
) -> None:
    reason = stop(record)["reason"]

    assert "say why" not in reason
