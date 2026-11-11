"""Stop-time model rules: the one result line, what only a block reason adds, and what the receipt records."""

import re
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import Tools, finding
from tests.hooks.model_rules_support import commit_file, edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import session_store

THREE_FILES = [("a.py", 12), ("b.py", 15), ("c.py", 8)]
SECONDS = r"\d+\.\ds"


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session in a repository of a trusted owner, after one edit."""
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


def receipt(record: session_store.SessionRecord) -> dict:
    return record.results()["model_rules"]


def jev_lint_line(result: dict) -> str:
    """The model rules' line of a Stop result, which follows the verification's own line."""
    assert "decision" not in result
    return result["systemMessage"].splitlines()[-1]


def test_a_clean_review_is_one_line_with_the_subjects_cost_and_seconds(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([])

    message = jev_lint_line(stop(record))

    assert re.fullmatch(rf"jev-lint: 0 findings · 1 subject · passed · \$0\.0011 · {SECONDS}", message)


def test_findings_that_cannot_block_are_the_one_line_alone(record: session_store.SessionRecord) -> None:
    message = jev_lint_line(stop(record, active=True))

    assert re.fullmatch(rf"jev-lint: 1 finding · 1 subject · advisory · \$0\.0011 · {SECONDS}", message)


def test_the_block_reason_adds_the_instruction_and_one_line_per_finding_without_the_rule_text(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.write_report([finding(), finding("other-rule", line=8)])

    lines = stop(record)["reason"].splitlines()

    assert re.fullmatch(rf"jev-lint: 2 findings · 1 subject · advisory · \$0\.0011 · {SECONDS}", lines[1])
    assert lines[2:] == [
        "Fix each one, or say why it does not apply.",
        "- command-query-naming · notes.txt:3",
        "- other-rule · notes.txt:8",
    ]


def test_the_cost_is_summed_over_the_two_reviews(record: session_store.SessionRecord, tools: Tools) -> None:
    commit_file(record, "committed.txt")
    tools.write_report([])

    message = stop(record)["systemMessage"]

    assert "· $0.0022 ·" in message


def test_the_line_tells_judged_over_total_subjects_when_the_cap_skipped_some(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)

    reason = stop(record)["reason"]

    assert "jev-lint: 1 finding · 20/35 subjects · advisory · " in reason


def test_a_finding_line_never_names_the_rule_text(record: session_store.SessionRecord) -> None:
    assert "the name promises a query" not in stop(record)["reason"]


def test_files_withheld_from_the_model_are_counted_at_the_end_of_the_line(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    (record.root / "link.txt").symlink_to(record.root / "notes.txt")
    tools.write_report([])

    message = stop(record)["systemMessage"]

    assert message.endswith(" · 1 withheld: links or outside the repository")


def test_unchanged_inputs_with_findings_are_one_line_and_run_nothing(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record)

    again = stop(record)

    assert jev_lint_line(again) == "jev-lint: 1 finding · unchanged; not rerun"
    assert len(tools.calls("op")) == 1


def test_unchanged_inputs_without_findings_are_one_line(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.write_report([])
    stop(record)

    assert jev_lint_line(stop(record)) == "jev-lint: 0 findings · unchanged; not rerun"


def test_findings_that_were_never_shown_block_later_with_the_instruction_and_the_findings(
    record: session_store.SessionRecord,
) -> None:
    stop(record, active=True)

    reason = stop(record)["reason"]

    assert reason.splitlines()[-3:] == [
        "jev-lint: 1 finding · unchanged; not rerun",
        "Fix each one, or say why it does not apply.",
        "- command-query-naming · notes.txt:3",
    ]


def test_a_review_that_did_not_run_is_one_skipped_line(
    record: session_store.SessionRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_MODEL_RULES", "off")

    assert jev_lint_line(stop(record)) == "jev-lint: skipped · AGENT_MODEL_RULES=off"


def test_the_receipt_records_requests_cached_seconds_and_cost_for_measuring_the_timing(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(10, [("a.py", 10)], cached=4)

    stop(record)

    saved = receipt(record)
    assert (saved["requests"], saved["cached"], saved["usd"]) == (2, 4, 0.0011)
    assert saved["seconds"] >= 0


def test_the_cap_counts_only_the_cached_subjects_of_the_files_it_kept(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES, cached=5)
    tools.write_plan_of_files(("a.py", "c.py"), subjects=20, cached=3)

    stop(record)

    assert receipt(record)["cached"] == 3


def test_a_count_that_cannot_be_read_stops_the_review_before_the_model_is_asked(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    tools.write_plan_of_files(("a.py", "c.py"), subjects=20, cached="many")

    result = stop(record)

    assert "printed a plan that cannot be read" in result["systemMessage"]
    assert tools.calls("op") == []


def test_the_receipt_counts_no_cached_subject_when_the_plan_has_none(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(10, [("a.py", 10)])

    stop(record)

    assert receipt(record)["cached"] == 0


def test_a_receipt_for_unchanged_inputs_is_reused_even_when_the_cap_skipped_subjects(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, THREE_FILES)
    stop(record, active=True)

    again = stop(record, active=True)

    assert "unchanged; not rerun" in again["systemMessage"]
    assert len(tools.calls("op")) == 1
