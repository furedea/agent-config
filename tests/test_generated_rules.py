"""P3 of #73: the Claude, Codex, and Devin rules generated from the shared prefixes decide like the source.

All three providers resolve overlapping prefixes to the strictest decision (Claude reads deny, ask,
then allow; Codex lets the most restrictive win; Devin's order is unconfirmed, and the strictest-wins
reading is the one assumed here). The decisions are compared on every prefix of the policy, its
shorter forms, and a longer form, which together cover each decision the trie can make.
"""

import json
from pathlib import Path

import pytest

from tests.generated_rules import (
    Rule,
    claude_rules,
    codex_rules,
    decide,
    decision_gaps,
    devin_rules,
    policy_rules,
)
from tests.runtime import REPO_ROOT, CliRunner

SOURCE = policy_rules(json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"])


def test_the_strictest_matching_prefix_decides() -> None:
    rules = [Rule(("git",), "allow"), Rule(("git", "push"), "ask"), Rule(("git", "push", "--force"), "deny")]
    assert decide(rules, ("git", "status")) == "allow"
    assert decide(rules, ("git", "push", "origin")) == "ask"
    assert decide(rules, ("git", "push", "--force", "origin")) == "deny"
    assert decide(rules, ("ls",)) is None


def test_a_prefix_matches_whole_words_only() -> None:
    assert decide([Rule(("git", "ad"), "allow")], ("git", "add")) is None


def test_identical_rules_have_no_gap() -> None:
    assert decision_gaps(SOURCE, SOURCE) == []


def test_a_widened_allow_is_a_gap_with_the_command_it_lets_through() -> None:
    gaps = decision_gaps(SOURCE, [*SOURCE, Rule(("git",), "allow")])
    assert gaps
    assert all(gap.generated == "allow" and gap.source != "allow" for gap in gaps)


def test_a_dropped_deny_is_a_gap() -> None:
    dropped = [rule for rule in SOURCE if rule != Rule(("op",), "deny")]
    assert [(gap.words, gap.source, gap.generated) for gap in decision_gaps(SOURCE, dropped)][:1] == [
        (("op",), "deny", None)
    ]


def test_a_decision_changed_in_place_is_a_gap() -> None:
    target = next(rule for rule in SOURCE if rule.decision == "allow")
    changed = [Rule(rule.prefix, "ask" if rule == target else rule.decision) for rule in SOURCE]
    gaps = decision_gaps(SOURCE, changed)
    assert (target.prefix, "allow", "ask") in {(gap.words, gap.source, gap.generated) for gap in gaps}


def test_a_missing_rule_for_a_longer_command_is_a_gap_even_when_the_prefix_is_covered() -> None:
    rules = [Rule(("git",), "allow"), Rule(("git", "push", "--force"), "deny")]
    gaps = decision_gaps(rules, [Rule(("git",), "allow")])
    assert (("git", "push", "--force"), "deny", "allow") in {(gap.words, gap.source, gap.generated) for gap in gaps}
    assert all(gap.words[:3] == ("git", "push", "--force") for gap in gaps)


def test_claude_bash_entries_are_read_as_prefixes_and_other_entries_are_ignored() -> None:
    permissions = {
        "allow": ["Bash(git status:*)", "Read"],
        "ask": ["Bash(dangerouslyDisableSandbox:true)", "Bash(rm:*)"],
        "deny": ["Bash(op:*)", "Read(**/.env)"],
    }
    assert claude_rules(permissions) == [
        Rule(("git", "status"), "allow"),
        Rule(("rm",), "ask"),
        Rule(("op",), "deny"),
    ]


def test_codex_prefix_rules_map_prompt_and_forbidden_to_ask_and_deny() -> None:
    text = """
prefix_rule(
    pattern = ["git","status"],
    decision = "allow",
    justification = "x",
)

prefix_rule(
    pattern = ["rm"],
    decision = "prompt",
    justification = "y",
)

prefix_rule(
    pattern = ["op"],
    decision = "forbidden",
    justification = "z",
)
"""
    assert codex_rules(text) == [
        Rule(("git", "status"), "allow"),
        Rule(("rm",), "ask"),
        Rule(("op",), "deny"),
    ]


def test_devin_exec_entries_are_read_as_prefixes() -> None:
    permissions = {"allow": ["Exec(git status)"], "ask": ["Exec(rm)"], "deny": ["Exec(op)"]}
    assert devin_rules(permissions) == [
        Rule(("git", "status"), "allow"),
        Rule(("rm",), "ask"),
        Rule(("op",), "deny"),
    ]


@pytest.mark.parametrize(
    "block",
    [
        'prefix_rule(decision = "allow", pattern = ["git"], justification = "x")',
        'prefix_rule(pattern = ["git", ["status", "log"]], decision = "allow")',
        'prefix_rule(pattern = ["git"], justification = "x", decision = "allow")',
        'prefix_rule(pattern = [], decision = "allow")',
        'prefix_rule(pattern = ["git"], decision = "maybe")',
    ],
)
def test_a_codex_rule_in_an_unknown_layout_is_refused_instead_of_skipped(block: str) -> None:
    text = f'prefix_rule(\n    pattern = ["ls"],\n    decision = "allow",\n)\n\n{block}\n'
    with pytest.raises(ValueError, match="unrecognized Codex rule"):
        codex_rules(text)


@pytest.mark.parametrize("entry", ["Bash", "Bash(git status)", "Bash(:*)", "Exec()"])
def test_an_entry_in_an_unknown_shape_is_refused_instead_of_skipped(entry: str) -> None:
    parsers = {"Bash": claude_rules, "Bash(git status)": claude_rules, "Bash(:*)": claude_rules, "Exec()": devin_rules}
    with pytest.raises(ValueError, match="unrecognized"):
        parsers[entry]({"allow": [entry]})


@pytest.mark.integration
def test_the_generated_claude_rules_decide_like_the_source(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    agent_harness("generate-claude-settings", "--output", str(path))
    assert decision_gaps(SOURCE, claude_rules(json.loads(path.read_text())["permissions"])) == []


@pytest.mark.integration
def test_the_generated_codex_rules_decide_like_the_source(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "default.rules"
    agent_harness("generate-codex-rules", "--output", str(path))
    assert decision_gaps(SOURCE, codex_rules(path.read_text())) == []


@pytest.mark.integration
def test_the_generated_devin_rules_decide_like_the_source(agent_harness: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "hooks.json"
    agent_harness("generate-devin-hooks", "--output", str(path))
    assert decision_gaps(SOURCE, devin_rules(json.loads(path.read_text())["permissions"])) == []
