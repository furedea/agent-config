"""The prefix audit reports conflicting, ineffective, and redundant command prefixes without changing them."""

import pytest

from tests.prefix_audit import Finding, audit_prefixes


def rule(decision: str, *prefix: str) -> dict:
    return {"prefix": list(prefix), "decision": decision, "justification": "test"}


def test_clean_rules_report_nothing() -> None:
    audit = audit_prefixes([rule("allow", "git", "status"), rule("ask", "rm"), rule("deny", "op")])
    assert (audit.conflicts, audit.ineffective, audit.redundant) == ((), (), ())


@pytest.mark.parametrize(
    ("first", "second"), [("allow", "deny"), ("deny", "allow"), ("allow", "ask"), ("ask", "deny")]
)
def test_one_prefix_with_two_decisions_is_a_conflict(first: str, second: str) -> None:
    audit = audit_prefixes([rule(first, "git", "push"), rule(second, "git", "push")])
    assert audit.conflicts == (Finding(("git", "push"), second, ("git", "push"), first),)


def test_a_duplicate_prefix_with_the_same_decision_is_redundant() -> None:
    audit = audit_prefixes([rule("allow", "ls"), rule("allow", "ls")])
    assert audit.redundant == (Finding(("ls",), "allow", ("ls",), "allow"),)
    assert audit.conflicts == ()


def test_a_narrower_prefix_under_the_same_decision_is_redundant() -> None:
    audit = audit_prefixes([rule("allow", "cargo", "fmt"), rule("allow", "cargo", "fmt", "--check")])
    assert audit.redundant == (Finding(("cargo", "fmt", "--check"), "allow", ("cargo", "fmt"), "allow"),)


@pytest.mark.parametrize(("ancestor", "narrow"), [("ask", "allow"), ("deny", "allow"), ("deny", "ask")])
def test_a_prefix_under_a_stricter_ancestor_never_takes_effect(ancestor: str, narrow: str) -> None:
    audit = audit_prefixes([rule(ancestor, "gh", "pr"), rule(narrow, "gh", "pr", "view")])
    assert audit.ineffective == (Finding(("gh", "pr", "view"), narrow, ("gh", "pr"), ancestor),)
    assert audit.redundant == ()


@pytest.mark.parametrize(("ancestor", "narrow"), [("allow", "deny"), ("allow", "ask"), ("ask", "deny")])
def test_a_stricter_exception_under_a_looser_ancestor_is_effective(ancestor: str, narrow: str) -> None:
    audit = audit_prefixes([rule(ancestor, "git", "branch"), rule(narrow, "git", "branch", "-D")])
    assert (audit.conflicts, audit.ineffective, audit.redundant) == ((), (), ())


def test_an_unrelated_prefix_sharing_leading_characters_is_not_an_ancestor() -> None:
    audit = audit_prefixes([rule("allow", "git", "log"), rule("allow", "git", "logx")])
    assert audit.redundant == ()


def test_the_audit_leaves_its_input_unchanged() -> None:
    rules = [rule("allow", "ls"), rule("allow", "ls", "-l")]
    before = [dict(item) for item in rules]
    audit_prefixes(rules)
    assert rules == before
