"""Stop-time model rules: when findings block, when they only notify, and which changes are judged."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import ENVIRONMENT_ID, FAKE_TOKEN, Tools, finding
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_gate
import session_gate
import session_store

HOOK = REPO_ROOT / "agents/hooks/verification_session.py"


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def registered(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session registered in a repository of a trusted owner, before any edit."""
    return register_session(git_project, tmp_path, monkeypatch)


@pytest.fixture
def record(registered: session_store.SessionRecord) -> session_store.SessionRecord:
    """The registered session after one edit."""
    edit(registered, "after\n")
    return registered


def test_new_findings_block_once_and_name_rule_and_location(record: session_store.SessionRecord) -> None:
    result = stop(record)

    assert result["decision"] == "block"
    assert "command-query-naming" in result["reason"]
    assert "notes.txt:3" in result["reason"]


def test_a_model_rules_block_keeps_the_verification_report(record: session_store.SessionRecord) -> None:
    result = stop(record)

    assert result["decision"] == "block"
    assert result["reason"].startswith("Verification skipped")
    assert "command-query-naming" in result["reason"]


def test_the_same_findings_on_unchanged_inputs_only_notify(record: session_store.SessionRecord, tools: Tools) -> None:
    stop(record)
    again = stop(record)

    assert "decision" not in again
    assert "unchanged; not rerun" in again["systemMessage"]
    assert len(tools.calls("op")) == 1


def test_findings_on_changed_inputs_block_again(record: session_store.SessionRecord, tools: Tools) -> None:
    stop(record)
    edit(record, "another edit\n")

    assert stop(record)["decision"] == "block"
    assert len(tools.calls("op")) == 2


def test_findings_never_block_again_after_the_agent_continued_because_of_a_stop_block(
    record: session_store.SessionRecord,
) -> None:
    result = stop(record, active=True)

    assert "decision" not in result
    assert "command-query-naming" in result["systemMessage"]


def test_findings_that_could_not_block_because_the_stop_hook_was_active_block_once_at_the_next_stop(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    unseen = stop(record, active=True)
    next_stop = stop(record)
    after_that = stop(record)

    assert "decision" not in unseen
    assert next_stop["decision"] == "block"
    assert "command-query-naming" in next_stop["reason"]
    assert "decision" not in after_that
    assert "unchanged; not rerun" in after_that["systemMessage"]
    assert len(tools.calls("op")) == 1


def test_unseen_findings_still_do_not_block_while_the_stop_hook_stays_active(
    record: session_store.SessionRecord,
) -> None:
    stop(record, active=True)

    assert "decision" not in stop(record, active=True)


def test_the_model_rules_get_only_the_time_the_stop_hook_has_left(
    record: session_store.SessionRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    budgets: list[float] = []

    def spy(_record: session_store.SessionRecord, **arguments: float) -> object:
        budgets.append(arguments["budget_seconds"])
        return model_rules_gate.Advice("spied")

    monkeypatch.setattr(model_rules_gate, "advise", spy)
    monkeypatch.setattr(session_gate, "STOP_TIMEOUT_SECONDS", 100)

    stop(record)

    assert 70 < budgets[0] <= 100 - session_gate.STOP_MARGIN_SECONDS


def test_no_model_rules_run_when_the_stop_hook_has_no_time_left(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_gate, "STOP_TIMEOUT_SECONDS", session_gate.STOP_MARGIN_SECONDS)

    result = stop(record)

    assert "decision" not in result
    assert "no time left" in result["systemMessage"]
    assert tools.calls() == []


def test_a_review_without_findings_only_notifies(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.report([])

    result = stop(record)

    assert "decision" not in result
    assert "no findings" in result["systemMessage"]


def test_nothing_to_judge_asks_the_model_nothing(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.plan(0)

    result = stop(record)

    assert "decision" not in result
    assert tools.calls("op") == []


def test_commits_made_since_registration_are_reviewed_from_the_starting_commit_then_the_uncommitted_changes(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    commit_file(record, "committed.txt")

    result = stop(record)

    committed, uncommitted = tools.calls("op")
    assert committed["argv"][committed["argv"].index("--base") + 1] == record.head
    assert committed["argv"][-1] == "committed.txt"
    assert "--base" not in uncommitted["argv"]
    assert "1 finding(s)" in result["reason"]


def test_the_cap_is_shared_by_the_two_reviews(record: session_store.SessionRecord, tools: Tools) -> None:
    commit_file(record, "committed.txt")
    tools.plan(15, [("a.py", 15)])

    result = stop(record)

    assert len(tools.calls("op")) == 1
    assert "15 subject(s) in 1 file(s) skipped by the cap of 20" in result["reason"]


def test_the_cap_keeps_whole_files_that_fit_and_reports_the_rest(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(35, [("a.py", 12), ("b.py", 15), ("c.py", 8)])

    result = stop(record)

    [launch] = tools.calls("op")
    assert launch["argv"][-2:] == ["a.py", "c.py"]
    assert "15 subject(s) in 1 file(s) skipped by the cap of 20" in result["reason"]


def test_subjects_already_cached_do_not_count_against_the_cap(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    tools.plan(30, [("a.py", 30)], cached=15)

    stop(record)

    [launch] = tools.calls("op")
    assert "a.py" not in launch["argv"]


def test_the_kill_switch_wins_over_a_stored_receipt_of_unseen_findings(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop(record, active=True)
    calls_before = len(tools.calls())
    monkeypatch.setenv("AGENT_MODEL_RULES", "off")

    result = stop(record)

    assert "decision" not in result
    assert "AGENT_MODEL_RULES=off" in result["systemMessage"]
    assert len(tools.calls()) == calls_before


def test_a_file_the_session_never_touched_is_not_sent_even_when_it_is_untracked(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    stop(record)

    arguments = [argument for call in tools.calls("jev-lint") for argument in call["argv"]]
    assert "preexisting.txt" not in arguments


def test_a_new_file_created_by_the_session_is_sent(record: session_store.SessionRecord, tools: Tools) -> None:
    (record.root / "created.txt").write_text("new\n")

    stop(record)

    [launch] = tools.calls("op")
    assert launch["argv"][-2:] == ["created.txt", "notes.txt"]


def commit_file(record: session_store.SessionRecord, name: str) -> None:
    (record.root / name).write_text("committed\n")
    subprocess.run(["git", "add", name], cwd=record.root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "later"], cwd=record.root, check=True)


def arguments_of_jev_lint(tools: Tools) -> list[str]:
    return [argument for call in tools.calls("jev-lint") for argument in call["argv"]]


@pytest.fixture
def secret(tmp_path: Path) -> Path:
    """A file outside the repository that must never be sent anywhere."""
    path = tmp_path.parent / f"{tmp_path.name}-outside" / "private-config"
    path.parent.mkdir()
    path.write_text("Host *\n  IdentityFile ~/.ssh/id_ed25519\n")
    return path


def test_a_symlink_to_a_file_outside_the_repository_is_not_sent_and_is_counted(
    record: session_store.SessionRecord, tools: Tools, secret: Path
) -> None:
    (record.root / "link.txt").symlink_to(secret)

    result = stop(record)

    arguments = arguments_of_jev_lint(tools)
    assert "link.txt" not in arguments
    assert "notes.txt" in arguments
    assert "1 file(s) withheld" in result["reason"]
    assert "link.txt" not in result["reason"]
    assert secret.name not in result["reason"]


def test_a_symlink_to_a_file_inside_the_repository_is_not_sent_either(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    (record.root / "alias.txt").symlink_to("notes.txt")

    result = stop(record)

    arguments = arguments_of_jev_lint(tools)
    assert "alias.txt" not in arguments
    assert "1 file(s) withheld" in result["reason"]


def test_a_file_reached_through_a_directory_replaced_by_a_link_is_not_sent(
    git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tools: Tools, secret: Path
) -> None:
    (git_project / "sub").mkdir()
    (git_project / "sub" / "file.txt").write_text("inside\n")
    record = register_session(git_project, tmp_path, monkeypatch)
    (git_project / "sub" / "file.txt").unlink()
    (git_project / "sub").rmdir()
    (git_project / "sub").symlink_to(secret.parent)
    (secret.parent / "file.txt").write_text("outside\n")

    result = stop(record)

    assert "sub/file.txt" not in arguments_of_jev_lint(tools)
    assert tools.calls("op") == []
    assert "withheld" in result["systemMessage"]


def test_only_links_changed_means_nothing_is_sent_and_the_notice_says_so(
    registered: session_store.SessionRecord, tools: Tools, secret: Path
) -> None:
    (registered.root / "link.txt").symlink_to(secret)

    result = stop(registered)

    assert "decision" not in result
    assert tools.calls("op") == []
    assert tools.calls("security") == []
    assert "1 file(s) withheld" in result["systemMessage"]
    assert "link.txt" not in result["systemMessage"]


def test_a_hard_link_to_a_file_outside_the_repository_is_not_sent(
    record: session_store.SessionRecord, tools: Tools, secret: Path
) -> None:
    os.link(secret, record.root / "second-name.txt")

    result = stop(record)

    arguments = arguments_of_jev_lint(tools)
    assert "second-name.txt" not in arguments
    assert "notes.txt" in arguments
    assert "1 file(s) withheld" in result["reason"]


def test_a_committed_symlink_is_not_sent_by_the_review_of_commits(
    record: session_store.SessionRecord, tools: Tools, secret: Path
) -> None:
    (record.root / "link.txt").symlink_to(secret)
    commit_file(record, "committed.txt")
    subprocess.run(["git", "add", "link.txt"], cwd=record.root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "link"], cwd=record.root, check=True)

    result = stop(record)

    arguments = arguments_of_jev_lint(tools)
    assert "link.txt" not in arguments
    assert "committed.txt" in arguments
    assert "1 file(s) withheld" in result["reason"]


def test_the_kill_switch_runs_nothing(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_MODEL_RULES", "off")

    result = stop(record)

    assert "decision" not in result
    assert "AGENT_MODEL_RULES=off" in result["systemMessage"]
    assert tools.calls() == []


def test_an_untrusted_repository_sends_nothing_and_reads_no_secret(
    record: session_store.SessionRecord, tools: Tools, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "other_owners.json"
    other.write_text(json.dumps({"owners": ["someone-else"], "exclude_forks": False}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(other))

    result = stop(record)

    assert "decision" not in result
    assert "not trusted" in result["systemMessage"]
    assert tools.calls() == []


@pytest.mark.parametrize("missing", ["agent-model-rules-op-token", "agent-model-rules-op-environment"])
def test_a_missing_keychain_item_skips_without_asking_the_model(
    record: session_store.SessionRecord, tools: Tools, missing: str
) -> None:
    items = {"agent-model-rules-op-token": FAKE_TOKEN, "agent-model-rules-op-environment": ENVIRONMENT_ID}
    tools.keychain(**{service: value for service, value in items.items() if service != missing})

    result = stop(record)

    assert "decision" not in result
    assert missing in result["systemMessage"]
    assert tools.calls("op") == [] and tools.calls("jev-lint") == []


def test_no_edit_since_registration_skips(registered: session_store.SessionRecord, tools: Tools) -> None:
    result = stop(registered)

    assert "no changes since session registration" in result["systemMessage"]
    assert tools.calls() == []


def test_the_stop_hook_blocks_through_the_provider_entry_point(
    record: session_store.SessionRecord, tmp_path: Path
) -> None:
    payload = {"cwd": str(record.root), "session_id": "model-rules"}

    first = _run_hook(payload, tmp_path / "bin")
    second = _run_hook({**payload, "stop_hook_active": True}, tmp_path / "bin")

    assert json.loads(first)["decision"] == "block"
    assert "decision" not in json.loads(second)


def test_findings_are_bounded_in_the_message(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.report([finding(line=number) for number in range(30)])

    reason = stop(record)["reason"]

    assert "... and 20 more" in reason


def test_the_gate_reports_a_receipt_input_that_includes_the_rules(record: session_store.SessionRecord) -> None:
    assert model_rules_gate.RULES_DIRECTORY.is_dir()
    before = record.results().get(model_rules_gate.RECEIPT_KEY)

    stop(record)

    assert before is None
    assert record.results()[model_rules_gate.RECEIPT_KEY]["outcome"] == "findings"


# The hook runs in its own process, so the fake store is installed there before the hook starts, as `install_fakes`
# does in this one.
HOOK_DRIVER = """
import os, runpy, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
import model_rules_programs
programs = Path(sys.argv[3])
model_rules_programs.DIRECTORIES = (programs,)
model_rules_programs.STORE_ROOT = programs.resolve()
model_rules_programs.TRUSTED_UID = os.getuid()
sys.argv = [sys.argv[1], "claude", "stop"]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def _run_hook(payload: dict, programs: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", HOOK_DRIVER, str(HOOK), str(REPO_ROOT / "agents/hooks/lib"), str(programs)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout
