"""P2: each allow prefix that is wider than a forbidden regex's carve-out is on a reviewed list.

An overlap is not a defect by itself: the provider allows the prefix and the hook denies the narrower
form, as for `git add` and `git add .`. The list below was reviewed for #73; a prefix that newly overlaps
a forbidden form, or one that stops overlapping because a rule was deleted, changes it and fails here.
"""

import json

from tests.rule_overlap import find_overlaps
from tests.runtime import REPO_ROOT


POLICY = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
FORBIDDEN = json.loads((REPO_ROOT / "agents/hooks/rules/forbidden_commands.json").read_text())["rules"]
ALLOW = [tuple(rule["prefix"]) for rule in POLICY if rule["decision"] == "allow"]
KEY_LENGTH = 40

# (allow prefix, the first KEY_LENGTH characters of the forbidden pattern it overlaps)
REVIEWED = {
    ("cargo mutants", "^cargo mutants .*--in-place"),
    ("git add", "^git[[:space:]]+add([[:space:]]+-[^[:spa"),
    ("git add", "(^|[[:space:]])git[[:space:]]+add([[:spa"),
    ("git commit", "^git[[:space:]]+commit([[:space:]].*)?[["),
    ("git commit", "(^|[[:space:]])git[[:space:]]+commit([[:"),
    ("uv run python", "(^|[[:space:]])python[0-9.]*([[:space:]]"),
    ("uv run python", "^uv run .*mutmut apply"),
    ("uv run --frozen python", "(^|[[:space:]])python[0-9.]*([[:space:]]"),
    ("uv run --frozen python", "^uv run .*mutmut apply"),
    ("uv run --frozen pytest", "^uv run .*mutmut apply"),
    ("uv run --frozen ruff", "^uv run .*mutmut apply"),
    ("uv run --frozen ty", "^uv run .*mutmut apply"),
    ("uv run --frozen bats", "^uv run .*mutmut apply"),
    ("uv run --frozen mutmut run", "^uv run .*mutmut apply"),
    ("uv run --frozen --group audit deptry", "^uv run .*mutmut apply"),
    ("uv run --frozen --group audit vulture", "^uv run .*mutmut apply"),
    ("python3", "(^|[[:space:]])python[0-9.]*([[:space:]]"),
    ("python", "(^|[[:space:]])python[0-9.]*([[:space:]]"),
    ("find", "(^|[[:space:]])find[[:space:]].*[[:space"),
    ("herdr agent start", "^herdr[[:space:]]+agent[[:space:]]+start"),
}


def overlap_keys(prefixes: list[tuple[str, ...]], rules: list[dict]) -> set[tuple[str, str]]:
    return {(" ".join(item.prefix), item.pattern[:KEY_LENGTH]) for item in find_overlaps(prefixes, rules)}


def test_the_overlaps_between_allow_prefixes_and_forbidden_rules_are_the_reviewed_ones() -> None:
    found = overlap_keys(ALLOW, FORBIDDEN)
    assert (found - REVIEWED, REVIEWED - found) == (set(), set())


def test_a_widened_allow_prefix_changes_the_overlaps() -> None:
    assert overlap_keys([*ALLOW, ("git",)], FORBIDDEN) != REVIEWED


def test_a_deleted_forbidden_rule_changes_the_overlaps() -> None:
    assert overlap_keys(ALLOW, FORBIDDEN[1:]) != REVIEWED
