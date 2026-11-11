"""What crosses the process boundary of the Stop-time model rules, and what each way of failing leaves behind."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from tests.hooks.model_rules_fakes import ENVIRONMENT_ID, FAKE_TOKEN, Tools
from tests.hooks.model_rules_support import edit, install_fakes, register_session, stop
from tests.runtime import REPO_ROOT, StubWriter

sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))
import model_rules_credentials
import model_rules_run
import session_store


@pytest.fixture(autouse=True)
def tools(executable: StubWriter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Tools:
    return install_fakes(executable, tmp_path, monkeypatch)


@pytest.fixture
def record(git_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> session_store.SessionRecord:
    """A session in a trusted repository, after one edit."""
    registered = register_session(git_project, tmp_path, monkeypatch)
    edit(registered, "after\n")
    return registered


def platform_free(names: list[str]) -> set[str]:
    """Variable names without the ones macOS adds to every exec, such as __CF_USER_TEXT_ENCODING."""
    return {name for name in names if not name.startswith("__CF")}


def test_the_model_is_asked_through_op_with_the_exact_argv(record: session_store.SessionRecord, tools: Tools) -> None:
    stop(record)

    [dry_run] = [call for call in tools.calls("jev-lint") if "--dry-run" in call["argv"]]
    [launch] = tools.calls("op")
    rules = str(REPO_ROOT / "agents/hooks/lint/model-rules")
    cache = str(Path(session_store.state_directory()).parent / "model-rules/verdicts.json")
    common = ["--json", "--no-config", "--fail-on", "error", "-R", rules, "-c", cache]
    # Only the file the session edited is named; `preexisting.txt` was already there and is left out.
    assert launch["argv"] == ["run", "--environment", ENVIRONMENT_ID, "--", "jev-lint", "review", *common, "notes.txt"]
    assert dry_run["argv"] == ["review", "--json", "--dry-run", *common[1:], "notes.txt"]
    assert dry_run["cwd"] == str(record.root.resolve())


def test_the_model_child_runs_under_its_own_deadline_so_it_ends_if_the_hook_is_killed(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_rules_run, "JUDGE_TIMEOUT_SECONDS", 7)

    stop(record)

    [wrapped] = [call for call in tools.calls("timeout") if "op" in call["argv"]]
    # Only what GNU and BSD `timeout` both accept: short options and a plain number of seconds.
    assert wrapped["argv"][:6] == ["-s", "TERM", "-k", "5", "7.000", "op"]
    assert wrapped["argv"][6:9] == ["run", "--environment", ENVIRONMENT_ID]
    assert all(call["argv"][:4] == ["-s", "TERM", "-k", "5"] for call in tools.calls("timeout"))


def test_without_timeout_at_its_path_the_child_still_runs_and_only_the_in_hook_kill_bounds_it(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(model_rules_run, "TIMEOUT_PROGRAM", str(tools.directory / "absent" / "timeout"))

    result = stop(record)

    assert result["decision"] == "block"
    assert tools.calls("timeout") == []
    assert [call["argv"][0] for call in tools.calls("op")] == ["run"]


def test_a_timeout_found_only_on_path_is_not_used(
    record: session_store.SessionRecord, tools: Tools, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `timeout` is on PATH (the fake directory is), but the hook names /usr/bin/timeout, so PATH cannot hijack it.
    monkeypatch.setattr(model_rules_run, "TIMEOUT_PROGRAM", "/usr/bin/timeout")

    stop(record)

    assert tools.calls("timeout") == []


@pytest.mark.parametrize("status", [124, 137, -9], ids=["expired", "killed-after", "kill-signal"])
def test_every_way_timeout_reports_an_expired_deadline_is_a_timeout(
    record: session_store.SessionRecord, tools: Tools, status: int
) -> None:
    tools.behave(timeout_status=status)

    result = stop(record)

    assert "decision" not in result
    assert "timed out" in result["systemMessage"]


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
