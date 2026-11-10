"""Project rules with program_path count only from a trusted owner, and never weaken the global policy."""

import json
from pathlib import Path
import subprocess

import pytest

from tests.hooks.pinned_program_support import (
    FORBIDDEN_RULES,
    GLOBAL_RULES,
    PINNED,
    guard,
    pinned_rule,
    policy,
    swe_conform_ledger_rule,
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
    PINNED[0] = str(path)
    return path


pytestmark = pytest.mark.usefixtures("isolated_project")


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
    decision = guard.decide("allowed", {"tool_input": {"command": f"{PINNED[0]} ping"}})
    assert decision.decision == "allow"
    assert "trusted_owners.json" in (decision.notice or "")
    # Without the rule the program is ungoverned: the hook has no opinion on any form, pinned or not,
    # and the provider's own permission rules decide, exactly as for any other unlisted program.
    assert verdict("fleetctl ping") == "allow"


@pytest.mark.usefixtures("project")
def test_a_project_without_a_github_origin_is_untrusted() -> None:
    decision = guard.decide("allowed", {"tool_input": {"command": f"{PINNED[0]} ping"}})
    assert "trusted_owners.json" in (decision.notice or "")


@pytest.mark.usefixtures("monkeypatch")
def test_a_project_rule_cannot_lift_a_global_forbidden_rule(project: Path) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    rule = {"programs": ["git"], "patterns": ["^git add \\.$"], "justification": "Try to allow git add ."}
    write_rules(project / ".agents/hooks/rules/allowed_commands.json", [rule])
    assert verdict("git add .", "forbidden") == "deny"
    assert verdict("git add .", "allowed") != "deny"


def test_a_project_rule_cannot_pin_a_program_the_global_rules_govern(project: Path, tmp_path: Path) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text("#!/bin/sh\n")
    gh.chmod(0o755)
    rule = {**pinned_rule(str(gh), "gh"), "patterns": ["^gh pr merge 1$"]}
    write_rules(project / ".agents/hooks/rules/allowed_commands.json", [rule])
    for command in (f"{gh} pr merge 1", "gh pr merge 1", "gh pr list"):
        decision = guard.decide("allowed", {"tool_input": {"command": command}})
        assert decision.decision == "deny"
        assert "global rules govern" in decision.reason


def test_a_trusted_project_cannot_replace_a_pin_the_global_rules_made(
    project: Path, program: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_origin(project, "https://github.com/acme/tool.git")
    rules = json.loads(GLOBAL_RULES.read_text())["rules"] + [pinned_rule(str(program))]
    monkeypatch.setenv("AGENT_ALLOWED_COMMAND_RULES", str(write_rules(tmp_path / "pinned.json", rules)))
    other = tmp_path / "project_bin" / "fleetctl"
    other.parent.mkdir()
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    write_rules(project / ".agents/hooks/rules/allowed_commands.json", [pinned_rule(str(other))])
    assert guard.decide("allowed", {"tool_input": {"command": f"{other} ping"}}).decision == "deny"
    assert guard.decide("allowed", {"tool_input": {"command": f"{program} ping"}}).decision == "deny"


def test_two_rules_pinning_one_program_to_different_paths_conflict() -> None:
    rules = [pinned_rule("/opt/a/fleetctl"), pinned_rule("/opt/b/fleetctl")]
    with pytest.raises(ValueError, match="conflicting program_path"):
        policy.pinned_programs(rules)
    assert policy.pinned_programs([pinned_rule("/opt/a/fleetctl"), pinned_rule("/opt/a/fleetctl")])


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


@pytest.mark.usefixtures("ledger")
def test_the_swe_conform_ledger_rule_is_ignored_in_an_untrusted_project(project: Path) -> None:
    set_origin(project, "https://github.com/someone/tool.git")
    decision = guard.decide("allowed", {"tool_input": {"command": f"PATH=/tmp/shadow ledger ping"}})
    assert decision.decision == "allow"
    assert "trusted_owners.json" in (decision.notice or "")


def test_the_shipped_global_rules_pin_no_program() -> None:
    assert policy.pinned_programs(policy.load_rules(GLOBAL_RULES)) == {}
    assert policy.pinned_programs(policy.load_rules(FORBIDDEN_RULES)) == {}
