"""Stop-time model rules: when findings block, when they only notify, and what crosses the process boundary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import ENVIRONMENT_ID, FAKE_TOKEN, Tools, finding, install_tools
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_credentials
import model_rules_gate
import model_rules_run
import session_gate
import session_store

HOOK = REPO_ROOT / "agents/hooks/verification_session.py"


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    monkeypatch.setenv("USER", "tester")
    monkeypatch.delenv("AGENT_MODEL_RULES", raising=False)
    # Outside the worktree: the fakes' call log changes on every run and must not count as an edit.
    return install_tools(executable, tmp_path.parent / f"{tmp_path.name}-fakes")


@pytest.fixture
def record(registered: session_store.SessionRecord) -> session_store.SessionRecord:
    """The registered session after one edit."""
    edit(registered, "after\n")
    return registered


@pytest.fixture
def registered(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session registered in a repository of a trusted owner, before any edit."""
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/furedea/fixture.git"], cwd=git_project, check=True
    )
    trusted = tmp_path / "trusted_owners.json"
    trusted.write_text(json.dumps({"owners": ["furedea"], "exclude_forks": True, "repositories": ["furedea/fixture"]}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(trusted))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path.parent / f"{tmp_path.name}-state"))
    (git_project / "notes.txt").write_text("before\n")
    return session_store.register(git_project, "claude", "model-rules")


def edit(record: session_store.SessionRecord, text: str) -> None:
    (record.root / "notes.txt").write_text(text)


def platform_free(names: list[str]) -> set[str]:
    """Variable names without the ones macOS adds to every exec, such as __CF_USER_TEXT_ENCODING."""
    return {name for name in names if not name.startswith("__CF")}


def stop(record: session_store.SessionRecord, *, active: bool = False) -> dict:
    return session_gate.stop(record, stop_hook_active=active)


def test_new_findings_block_once_and_name_rule_and_location(record: session_store.SessionRecord) -> None:
    result = stop(record)

    assert result["decision"] == "block"
    assert "command-query-naming" in result["reason"]
    assert "notes.txt:3" in result["reason"]


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


def test_the_model_is_asked_through_op_with_the_exact_argv(record: session_store.SessionRecord, tools: Tools) -> None:
    stop(record)

    [dry_run] = [call for call in tools.calls("jev-lint") if "--dry-run" in call["argv"]]
    [launch] = tools.calls("op")
    rules = str(REPO_ROOT / "agents/hooks/lint/model-rules")
    cache = str(Path(session_store.state_directory()).parent / "model-rules/verdicts.json")
    common = ["--json", "--no-config", "--fail-on", "error", "-R", rules, "-c", cache]
    assert launch["argv"] == ["run", "--environment", ENVIRONMENT_ID, "--", "jev-lint", "review", *common]
    assert dry_run["argv"] == ["review", "--json", "--dry-run", *common[1:]]
    assert dry_run["cwd"] == str(record.root.resolve())


def test_only_the_op_process_receives_the_token_and_only_allowlisted_variables(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("JEV_LINT_CACHE", "none")
    allowed = set(model_rules_run.ENVIRONMENT_ALLOWLIST) | {"OP_SERVICE_ACCOUNT_TOKEN"}

    stop(record)

    [launch] = tools.calls("op")
    [dry_run] = [call for call in tools.calls("jev-lint") if "--dry-run" in call["argv"]]
    assert launch["has_token"]
    assert platform_free(launch["env_names"]) <= allowed
    assert not dry_run["has_token"]
    assert platform_free(dry_run["env_names"]) <= allowed
    assert all(FAKE_TOKEN not in argument for call in tools.calls() for argument in call["argv"])


def test_the_token_never_reaches_the_output_even_when_a_tool_prints_it(record: session_store.SessionRecord) -> None:
    result = stop(record)

    assert FAKE_TOKEN not in json.dumps(result)


def test_commits_made_since_registration_are_reviewed_from_the_starting_commit_then_the_uncommitted_changes(
    record: session_store.SessionRecord, tools: Tools
) -> None:
    subprocess.run(["git", "commit", "--quiet", "--allow-empty", "-m", "later"], cwd=record.root, check=True)

    result = stop(record)

    committed, uncommitted = tools.calls("op")
    assert committed["argv"][committed["argv"].index("--base") + 1] == record.head
    assert "--base" not in uncommitted["argv"]
    assert "1 finding(s)" in result["reason"]


def test_the_cap_is_shared_by_the_two_reviews(record: session_store.SessionRecord, tools: Tools) -> None:
    subprocess.run(["git", "commit", "--quiet", "--allow-empty", "-m", "later"], cwd=record.root, check=True)
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


@pytest.mark.parametrize("program", ["jev-lint", "op"])
def test_a_missing_program_skips(
    record: session_store.SessionRecord, monkeypatch: pytest.MonkeyPatch, program: str
) -> None:
    installed = shutil.which(program)
    assert installed is not None
    # Only the fakes and the system directories: a real `op` or `jev-lint` of the developer must not be found.
    monkeypatch.setenv("PATH", os.pathsep.join([str(Path(installed).parent), "/usr/bin", "/bin"]))
    Path(installed).unlink()

    result = stop(record)

    assert "decision" not in result
    assert f"{program} is not installed" in result["systemMessage"]


@pytest.mark.parametrize(
    ("behavior", "reason"),
    [({"exit": 3}, "exited with status 3"), ({"sleep": 5}, "timed out")],
    ids=["non-zero-exit", "timeout"],
)
def test_a_failed_review_only_notifies(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch, behavior: dict, reason: str
) -> None:
    monkeypatch.setattr(model_rules_run, "JUDGE_TIMEOUT_SECONDS", 0.5)
    tools.behave(**behavior)

    result = stop(record)

    assert "decision" not in result
    assert reason in result["systemMessage"]


@pytest.mark.parametrize("output", ["not json", '{"findings": 3}', '{"findings": [], "errors": ["x"]}'])
def test_an_unreadable_report_only_notifies(record: session_store.SessionRecord, tools: Tools, output: str) -> None:
    tools.raw_report(output)

    result = stop(record)

    assert "decision" not in result
    assert "Model rules skipped" in result["systemMessage"]


def test_a_prevented_run_is_tried_again_at_the_next_stop(record: session_store.SessionRecord, tools: Tools) -> None:
    tools.behave(exit=3)
    stop(record)
    tools.behave()

    assert stop(record)["decision"] == "block"


def test_another_session_holding_the_cache_lock_skips_the_run(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_rules_run, "LOCK_TIMEOUT_SECONDS", 0.2)
    cache = model_rules_run.cache_path(session_store.state_directory())
    session_store.private_directory(cache.parent)

    with session_store.file_lock(cache.parent / ".lock"):
        result = stop(record)

    assert "decision" not in result
    assert "lock" in result["systemMessage"]
    assert tools.calls("op") == []


def test_no_edit_since_registration_skips(registered: session_store.SessionRecord, tools: Tools) -> None:
    result = stop(registered)

    assert "no changes since session registration" in result["systemMessage"]
    assert tools.calls() == []


def test_the_stop_hook_blocks_through_the_provider_entry_point(record: session_store.SessionRecord) -> None:
    payload = {"cwd": str(record.root), "session_id": "model-rules"}

    first = _run_hook(payload)
    second = _run_hook({**payload, "stop_hook_active": True})

    assert json.loads(first)["decision"] == "block"
    assert "decision" not in json.loads(second)


def test_the_credentials_come_from_the_two_keychain_items_of_the_current_user(tools: Tools) -> None:
    credentials = model_rules_credentials.load()

    assert credentials == model_rules_credentials.Credentials(FAKE_TOKEN, ENVIRONMENT_ID)
    assert [call["argv"] for call in tools.calls("security")] == [
        ["find-generic-password", "-a", "tester", "-s", "agent-model-rules-op-token", "-w"],
        ["find-generic-password", "-a", "tester", "-s", "agent-model-rules-op-environment", "-w"],
    ]


def test_an_environment_id_need_not_be_a_uuid_but_must_be_lowercase_alphanumeric(tools: Tools) -> None:
    tools.keychain(**{"agent-model-rules-op-token": FAKE_TOKEN, "agent-model-rules-op-environment": "NOT-valid"})

    assert isinstance(model_rules_credentials.load(), model_rules_credentials.Prevented)


def test_credentials_do_not_show_the_token_in_their_representation() -> None:
    assert FAKE_TOKEN not in repr(model_rules_credentials.Credentials(FAKE_TOKEN, ENVIRONMENT_ID))


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


def _run_hook(payload: dict) -> str:
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(HOOK), "claude", "stop"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout
