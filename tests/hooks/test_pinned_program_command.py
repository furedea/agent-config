"""A rule's program_path lets its program run unprompted only as one literal call by an absolute path."""

import json
import os
from pathlib import Path

import pytest
from tests.hooks.pinned_program_support import (
    GLOBAL_RULES,
    PINNED,
    guard,
    pinned_rule,
    policy,
    verdict,
    write_rules,
)


@pytest.fixture
def program(tmp_path: Path) -> Path:
    """The pinned program: an executable regular file at an absolute temp path."""
    path = tmp_path / "pinned" / "fleetctl"
    path.parent.mkdir()
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def global_pin(program: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Global allowed rules plus the pinned example rule."""
    rules = json.loads(GLOBAL_RULES.read_text())["rules"] + [pinned_rule(str(program))]
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(write_rules(tmp_path / "allowed.json", rules)))
    return program


@pytest.fixture(autouse=True)
def installed_path(program: Path) -> None:
    PINNED[0] = str(program)


pytestmark = pytest.mark.usefixtures("isolated_project", "global_pin")


@pytest.mark.parametrize(
    "command",
    [
        "@fleetctl ping",
        "@fleetctl status",
        "@fleetctl status --target web-1 --target web_2",
        "@fleetctl run --target web-1 --note 'rolled back'",
        "@fleetctl run --target web-1 --note rollback",
    ],
)
def test_a_listed_form_by_the_pinned_absolute_path_runs_without_a_prompt(command: str) -> None:
    assert verdict(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "fleetctl ping",
        "./fleetctl ping",
        "pinned/fleetctl ping",
        "/tmp/fleetctl ping",
        "/usr/bin/fleetctl ping",
        "@fleetctl",
        "@fleetctl frobnicate",
        "@fleetctl ping --extra",
        "@fleetctl status --target",
        "@fleetctl status --target 'a;b'",
        "@fleetctl run --target web-1",
        "@fleetctl --config /tmp/x ping",
    ],
)
def test_the_bare_name_other_paths_and_unlisted_forms_ask(command: str) -> None:
    assert verdict(command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "PATH=/tmp/shadow @fleetctl ping",
        "FOO=1 @fleetctl ping",
        "LD_PRELOAD=/tmp/x.so @fleetctl ping",
        "PATH=/tmp/shadow command @fleetctl ping",
        "PATH=/tmp/shadow exec @fleetctl ping",
        "env PATH=/tmp/shadow @fleetctl ping",
        "env -i @fleetctl ping",
        "command @fleetctl ping",
        "exec @fleetctl ping",
        "nohup @fleetctl ping",
        "nice @fleetctl ping",
        "timeout 5 @fleetctl ping",
        "xargs @fleetctl ping",
        "sudo @fleetctl ping",
    ],
)
def test_an_assignment_or_wrapper_before_the_program_asks(command: str) -> None:
    assert verdict(command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "export PATH=/tmp/shadow && @fleetctl ping",
        "PATH=/tmp/shadow; @fleetctl ping",
        "hash -p /tmp/shadow/fleetctl fleetctl; @fleetctl ping",
        "cd /tmp/shadow && @fleetctl ping",
        "git status && @fleetctl ping",
        "@fleetctl ping && git status",
        "@fleetctl ping; @fleetctl ping",
        "echo x | @fleetctl status",
        "@fleetctl ping | cat",
        "@fleetctl ping &",
        "! @fleetctl ping",
        "( @fleetctl ping )",
        "{ @fleetctl ping; }",
        "if true; then @fleetctl ping; fi",
        "@fleetctl ping > /tmp/out",
        "@fleetctl ping < /dev/null",
        "bash -c '@fleetctl ping'",
        "sh -c 'PATH=/tmp/shadow @fleetctl ping'",
    ],
)
def test_another_statement_a_pipe_a_redirect_or_a_shell_asks(command: str) -> None:
    assert verdict(command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        '@fleetctl status --target "$((HOME=0))"',
        "@fleetctl status --target $((HOME=0))",
        "@fleetctl status --target $(id)",
        "@fleetctl status --target \"$(python3 -c 'print(1)')\"",
        '@fleetctl status --target "`id`"',
        '@fleetctl status --target "$TARGET"',
        "@fleetctl status --target $TARGET",
        "@fleetctl status --target ${TARGET:=x}",
        "@fleetctl status --target <(id)",
        "@fleetctl status --target ~",
        "@fleetctl status --target web-*",
        "@fleetctl status --target web-?",
        "@fleetctl status --target w{1,2}",
        '@fleetctl run --target web-1 --note "$((HOME=0))"',
    ],
)
def test_an_expansion_in_any_word_asks(command: str) -> None:
    assert verdict(command) == "ask"


def test_single_quoted_text_is_literal() -> None:
    assert verdict("@fleetctl run --target web-1 --note 'costs $5 and $(id) and *'") == "allow"


@pytest.mark.parametrize("quoted", ["'--extra'", '"--extra"', "\\--extra"])
def test_a_quoted_option_that_could_hide_from_the_listing_asks(quoted: str) -> None:
    assert verdict(f"@fleetctl status {quoted}") == "ask"


def test_a_missing_file_asks(program: Path) -> None:
    program.unlink()
    assert verdict("@fleetctl ping") == "ask"


def test_a_file_that_is_not_executable_asks(program: Path) -> None:
    program.chmod(0o644)
    assert verdict("@fleetctl ping") == "ask"


def test_a_directory_in_place_of_the_file_asks(program: Path) -> None:
    program.unlink()
    program.mkdir()
    assert verdict("@fleetctl ping") == "ask"


def test_a_shadow_earlier_on_path_cannot_change_what_the_absolute_path_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "fleetctl").write_text("#!/bin/sh\n")
    (shadow / "fleetctl").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shadow}{os.pathsep}{os.environ['PATH']}")
    assert verdict("fleetctl ping") == "ask"
    assert verdict("@fleetctl ping") == "allow"


def test_a_program_without_a_pinned_rule_is_left_to_the_other_rules() -> None:
    assert verdict("fleetctl-other ping") == "allow"
    assert verdict("git status") == "allow"


@pytest.mark.usefixtures("program")
def test_the_pin_does_not_run_for_the_forbidden_guard() -> None:
    assert verdict("@fleetctl ping", "forbidden") == "allow"
    assert verdict("@fleetctl ping && git add .", "forbidden") == "deny"


def test_removing_the_pin_changes_the_verdict(program: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fails if program_path enforcement is dropped: the same rule without the pin lets the bare name through."""
    unpinned = {key: value for key, value in pinned_rule(str(program)).items() if key != "program_path"}
    rules = json.loads(GLOBAL_RULES.read_text())["rules"] + [unpinned]
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(write_rules(tmp_path / "unpinned.json", rules)))
    assert verdict("PATH=/tmp/shadow fleetctl ping") == "allow"
    monkeypatch.setenv(
        "AGENT_ALLOWED_COMMAND_RULES",
        str(
            write_rules(
                tmp_path / "pinned.json", json.loads(GLOBAL_RULES.read_text())["rules"] + [pinned_rule(str(program))]
            )
        ),
    )
    assert verdict("PATH=/tmp/shadow fleetctl ping") == "ask"


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"program_path": "fleetctl"}, id="relative"),
        pytest.param({"program_path": "./fleetctl"}, id="dot"),
        pytest.param({"program_path": "/usr/local/../bin/fleetctl"}, id="parent"),
        pytest.param({"program_path": "/usr//local/bin/fleetctl"}, id="double slash"),
        pytest.param({"program_path": "/usr/local/bin/fleetctl/"}, id="trailing slash"),
        pytest.param({"program_path": "/usr/local/bin/*"}, id="glob"),
        pytest.param({"program_path": "~/bin/fleetctl"}, id="tilde"),
        pytest.param({"program_path": "/usr/local/bin/flee tctl", "programs": ["flee tctl"]}, id="space"),
        pytest.param({"program_path": "/"}, id="root"),
        pytest.param({"program_path": 5}, id="type"),
        pytest.param({"program_path": "/usr/local/bin/other"}, id="program name mismatch"),
        pytest.param({"programs": ["fleetctl", "other"]}, id="two programs"),
    ],
)
def test_an_invalid_program_path_is_rejected(tmp_path: Path, change: dict) -> None:
    rule = {**pinned_rule("/usr/local/bin/fleetctl"), **change}
    path = write_rules(tmp_path / "rules.json", [rule])
    with pytest.raises(ValueError, match="invalid command policy"):
        policy.load_rules(path)


def test_a_valid_program_path_is_accepted(tmp_path: Path) -> None:
    path = write_rules(tmp_path / "rules.json", [pinned_rule("/usr/local/bin/fleetctl")])
    assert policy.pinned_programs(policy.load_rules(path)) == {"fleetctl": "/usr/local/bin/fleetctl"}


def test_a_program_path_without_a_program_list_is_rejected(tmp_path: Path) -> None:
    rule = {key: value for key, value in pinned_rule("/usr/local/bin/fleetctl").items() if key != "programs"}
    with pytest.raises(ValueError, match="invalid command policy"):
        policy.load_rules(write_rules(tmp_path / "rules.json", [rule]))


@pytest.mark.parametrize("word", ["=fleetctl", '"=fleetctl"', "'=fleetctl'"])
def test_a_zsh_equals_expansion_of_the_program_name_asks(word: str) -> None:
    assert verdict(f"{word} ping") == "ask"


def test_the_equals_expansion_of_a_pinned_program_whose_file_is_missing_still_asks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = {**pinned_rule("/nonexistent/true", "true"), "patterns": ["^true$"]}
    rules = json.loads(GLOBAL_RULES.read_text())["rules"] + [rule]
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(write_rules(tmp_path / "true_rules.json", rules)))
    assert verdict("=true") == "ask"
    assert verdict("true") == "ask"


def test_an_equals_word_anywhere_in_the_line_asks() -> None:
    assert verdict("@fleetctl status --target =web") == "ask"
    assert verdict("@fleetctl run --target web-1 --note 'a =b'") == "allow"


@pytest.fixture
def pinned_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Git pinned to a temp path, whose listed form must not let git options through."""
    git = tmp_path / "gitbin" / "git"
    git.parent.mkdir()
    git.write_text("#!/bin/sh\n")
    git.chmod(0o755)
    rule = {
        "programs": ["git"],
        "program_path": str(git),
        "patterns": ["^git status$"],
        "justification": "Allow only git status.",
    }
    rules = json.loads(GLOBAL_RULES.read_text())["rules"] + [rule]
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(write_rules(tmp_path / "git_rules.json", rules)))
    return git


@pytest.mark.parametrize(
    "arguments",
    [
        "-c core.fsmonitor=/tmp/evil status",
        "-C /tmp status",
        "--git-dir=/tmp/x status",
        "status --porcelain",
        "log",
    ],
)
def test_options_the_git_canonical_form_drops_do_not_pass_the_listing(pinned_git: Path, arguments: str) -> None:
    assert guard.decide("allowed", {"tool_input": {"command": f"{pinned_git} {arguments}"}}).decision == "ask"
    assert guard.decide("allowed", {"tool_input": {"command": f"{pinned_git} status"}}).decision == "allow"
