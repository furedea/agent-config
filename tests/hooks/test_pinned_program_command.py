"""A rule's program_path lets its program run unprompted only as one literal call by that absolute path."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
policy = load_script_module("agents/hooks/lib/command_policy.py", "command_policy")
GLOBAL_RULES = REPO_ROOT / "agents/hooks/rules/allowed_commands.json"
FORBIDDEN_RULES = REPO_ROOT / "agents/hooks/rules/forbidden_commands.json"
NAME = "[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
SUBCOMMANDS = ("ping", "report", "claim", "status", "release", "result")


def pinned_rule(path: str, program: str = "fleetctl") -> dict:
    """An example rule for a program that is not part of the shipped policy."""
    return {
        "programs": [program],
        "program_path": path,
        "patterns": [
            f"^{program} ping$",
            f"^{program} status( --target {NAME})*$",
            f"^{program} run --target {NAME} --note ('[^']*'|[A-Za-z0-9_]+)$",
        ],
        "justification": "Allow the example tool in its documented forms.",
    }


def swe_conform_ledger_rule() -> dict:
    """The rule swe-conform would ship: six subcommands, no hold, pinned to the installed wrapper."""
    name = "[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
    text = "('[^']*'|\"[^\"$`\\\\!]*\"|[A-Za-z0-9_][A-Za-z0-9._-]*)"
    common = f" --failure {name}| --request-id {name}"
    return {
        "programs": ["ledger"],
        "program_path": "/usr/local/bin/ledger",
        "patterns": [
            "^ledger ping$",
            f"^ledger report({common}| --body {text})*$",
            f"^ledger claim({common})*$",
            f"^ledger status({common})*$",
            f"^ledger release({common}| --generation [0-9]+)*$",
            f"^ledger result({common}| --generation [0-9]+| --result {text})*$",
        ],
        "justification": "Allow the fleet ledger's local spool commands in their documented forms; every other form asks.",
    }


def write_rules(path: Path, rules: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "rules": rules}))
    return path


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


def verdict(command: str, kind: str = "allowed") -> str:
    return guard.decide(kind, {"tool_input": {"command": command.replace("@fleetctl", PATH[0])}}).decision


PATH: list[str] = [""]


@pytest.fixture(autouse=True)
def installed_path(program: Path) -> None:
    PATH[0] = str(program)


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


def test_a_program_without_a_pinned_rule_is_left_to_the_other_rules(tmp_path: Path) -> None:
    assert verdict("fleetctl-other ping") == "allow"
    assert verdict("git status") == "allow"


def test_the_pin_does_not_run_for_the_forbidden_guard(program: Path) -> None:
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
    ("change", "reason"),
    [
        ({"program_path": "fleetctl"}, "relative"),
        ({"program_path": "./fleetctl"}, "dot"),
        ({"program_path": "/usr/local/../bin/fleetctl"}, "parent"),
        ({"program_path": "/usr//local/bin/fleetctl"}, "double slash"),
        ({"program_path": "/usr/local/bin/fleetctl/"}, "trailing slash"),
        ({"program_path": "/usr/local/bin/*"}, "glob"),
        ({"program_path": "~/bin/fleetctl"}, "tilde"),
        ({"program_path": "/usr/local/bin/flee tctl", "programs": ["flee tctl"]}, "space"),
        ({"program_path": "/"}, "root"),
        ({"program_path": 5}, "type"),
        ({"program_path": "/usr/local/bin/other"}, "program name mismatch"),
        ({"programs": ["fleetctl", "other"]}, "two programs"),
    ],
)
def test_an_invalid_program_path_is_rejected(tmp_path: Path, change: dict, reason: str) -> None:
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


@pytest.fixture
def project(git_project: Path, program: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository whose own rules pin the example program; the global rules are the shipped ones."""
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(GLOBAL_RULES))
    write_rules(git_project / ".agents/hooks/rules/allowed_commands.json", [pinned_rule(str(program))])
    owners = tmp_path / "owners.json"
    owners.write_text(json.dumps({"owners": ["acme"], "exclude_forks": False}))
    monkeypatch.setenv("AGENT_TRUSTED_OWNERS", str(owners))
    return git_project


def set_origin(project: Path, url: str) -> None:
    subprocess.run(["git", "remote", "add", "origin", url], cwd=project, check=True, capture_output=True)


def test_a_trusted_project_rule_pins_its_program(project: Path) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    assert verdict("@fleetctl ping") == "allow"
    assert verdict("PATH=/tmp/shadow @fleetctl ping") == "ask"
    assert verdict("fleetctl ping") == "ask"
    assert verdict("@fleetctl status --target web-1 --extra") == "ask"


def test_an_untrusted_project_rule_is_ignored_and_never_widens_anything(project: Path) -> None:
    set_origin(project, "https://github.com/someone/tool.git")
    decision = guard.decide("allowed", {"tool_input": {"command": f"{PATH[0]} ping"}})
    assert decision.decision == "allow"
    assert "trusted_owners.json" in (decision.notice or "")
    # Without the rule the program is ungoverned: the hook has no opinion on any form, pinned or not,
    # and the provider's own permission rules decide, exactly as for any other unlisted program.
    assert verdict("fleetctl ping") == "allow"


def test_a_project_without_a_github_origin_is_untrusted(project: Path) -> None:
    decision = guard.decide("allowed", {"tool_input": {"command": f"{PATH[0]} ping"}})
    assert "trusted_owners.json" in (decision.notice or "")


def test_a_project_rule_cannot_lift_a_global_forbidden_rule(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    rule = {"programs": ["git"], "patterns": ["^git add \\.$"], "justification": "Try to allow git add ."}
    write_rules(project / ".agents/hooks/rules/allowed_commands.json", [rule])
    assert verdict("git add .", "forbidden") == "deny"
    assert verdict("git add .", "allowed") != "deny"


def test_a_project_rule_cannot_pin_a_program_to_a_path_for_a_global_governed_program(project: Path) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    rule = {**pinned_rule("/usr/local/bin/gh", "gh"), "patterns": ["^gh pr merge 1$"]}
    write_rules(project / ".agents/hooks/rules/allowed_commands.json", [rule])
    assert verdict("gh pr merge 1") == "ask"
    assert verdict("/usr/local/bin/gh pr merge 1") == "ask"


def swe_conform_project(project: Path, path: str) -> None:
    write_rules(
        project / ".agents/hooks/rules/allowed_commands.json", [{**swe_conform_ledger_rule(), "program_path": path}]
    )


@pytest.fixture
def ledger(program: Path, project: Path) -> Path:
    """The swe-conform rule, pinned to a stand-in path so the test never needs /usr/local/bin/ledger."""
    stand_in = program.parent / "ledger"
    stand_in.write_text("#!/bin/sh\n")
    stand_in.chmod(0o755)
    swe_conform_project(project, str(stand_in))
    return stand_in


@pytest.mark.parametrize(
    "arguments",
    [
        "ping",
        "report --failure build-42 --body 'pytest failed'",
        'report --failure build-42 --request-id r1 --body "pytest failed"',
        "claim --failure build-42",
        "status --failure build-42",
        "release --failure build-42 --generation 3",
        "result --failure build-42 --generation 3 --result fixed",
    ],
)
def test_the_swe_conform_ledger_rule_runs_its_six_subcommands_in_a_trusted_project(
    project: Path, ledger: Path, arguments: str
) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    assert verdict(f"{ledger} {arguments}") == "allow"


@pytest.mark.parametrize(
    "arguments",
    [
        "hold --failure build-42 -- git status",
        "--spool-root /tmp/fake ping",
        "--timeout 600 ping",
        "report --failure build-42 --spool-root /tmp/fake",
        "ping --extra",
        "frobnicate",
        "",
    ],
)
def test_the_swe_conform_ledger_rule_asks_for_hold_and_every_other_form(
    project: Path, ledger: Path, arguments: str
) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    assert verdict(f"{ledger} {arguments}".strip()) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "ledger ping",
        "PATH=/tmp/shadow @ledger ping",
        "env PATH=/tmp/shadow @ledger ping",
        "echo body | @ledger report --failure build-42",
        '@ledger claim --failure "$((HOME=0))"',
        "@ledger hold --failure f -- git status",
    ],
)
def test_the_swe_conform_ledger_rule_closes_the_earlier_bypasses(project: Path, ledger: Path, command: str) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    assert verdict(command.replace("@ledger", str(ledger))) == "ask"


def test_the_swe_conform_ledger_rule_is_ignored_in_an_untrusted_project(project: Path, ledger: Path) -> None:
    set_origin(project, "https://github.com/someone/tool.git")
    decision = guard.decide("allowed", {"tool_input": {"command": f"PATH=/tmp/shadow ledger ping"}})
    assert decision.decision == "allow"
    assert "trusted_owners.json" in (decision.notice or "")


def test_the_shipped_global_rules_pin_no_program() -> None:
    assert policy.pinned_programs(policy.load_rules(GLOBAL_RULES)) == {}
    assert policy.pinned_programs(policy.load_rules(FORBIDDEN_RULES)) == {}
