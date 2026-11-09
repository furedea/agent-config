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

GIT_ADD = (
    r"git[[:space:]]+add([[:space:]]+-[^[:space:]]*)*[[:space:]]+(\./?|-[A-Za-z]*A[A-Za-z]*|--all)([[:space:]]|$)"
)
GIT_COMMIT = (
    r"git[[:space:]]+commit([[:space:]].*)?[[:space:]]+(--no-verify|-[aeiopqsvz]*n[^[:space:]]*)([[:space:]]|$)"
)
PIP = r"(^|[[:space:]])python[0-9.]*([[:space:]]+-[A-Za-z]+)*[[:space:]]+-[A-Za-z]*m[[:space:]]*(pip|ensurepip)([[:space:]]|$)"
FIND = r"(^|[[:space:]])find[[:space:]].*[[:space:]]-(delete|exec|execdir|ok|okdir|fprint|fprint0|fprintf|fls)([[:space:]]|$)"
HERDR = r"^herdr[[:space:]]+agent[[:space:]]+start([[:space:]].*)?[[:space:]]--([[:space:]]|$)"
CARGO = "^cargo mutants .*--in-place"
MUTMUT = "^uv run .*mutmut apply"

# (allow prefix, the whole forbidden pattern it overlaps)
REVIEWED = {
    ("cargo mutants", CARGO),
    ("git add", "^" + GIT_ADD),
    ("git add", "(^|[[:space:]])" + GIT_ADD),
    ("git commit", "^" + GIT_COMMIT),
    ("git commit", "(^|[[:space:]])" + GIT_COMMIT),
    ("uv run python", PIP),
    ("uv run python", MUTMUT),
    ("uv run --frozen python", PIP),
    ("uv run --frozen python", MUTMUT),
    ("uv run --frozen pytest", MUTMUT),
    ("uv run --frozen ruff", MUTMUT),
    ("uv run --frozen ty", MUTMUT),
    ("uv run --frozen bats", MUTMUT),
    ("uv run --frozen mutmut run", MUTMUT),
    ("uv run --frozen --group audit deptry", MUTMUT),
    ("uv run --frozen --group audit vulture", MUTMUT),
    ("python3", PIP),
    ("python", PIP),
    ("find", FIND),
    ("herdr agent start", HERDR),
}


def overlap_keys(prefixes: list[tuple[str, ...]], rules: list[dict]) -> set[tuple[str, str]]:
    return {(" ".join(item.prefix), item.pattern) for item in find_overlaps(prefixes, rules)}


def test_the_overlaps_between_allow_prefixes_and_forbidden_rules_are_the_reviewed_ones() -> None:
    found = overlap_keys(ALLOW, FORBIDDEN)
    assert (found - REVIEWED, REVIEWED - found) == (set(), set())


def test_a_widened_allow_prefix_changes_the_overlaps() -> None:
    assert overlap_keys([*ALLOW, ("git",)], FORBIDDEN) != REVIEWED


def test_a_deleted_forbidden_rule_changes_the_overlaps() -> None:
    assert overlap_keys(ALLOW, FORBIDDEN[1:]) != REVIEWED


def test_patterns_that_share_a_long_start_are_distinct_overlaps() -> None:
    shared = "^git add " + "x" * 60
    rules = [{"patterns": [shared + "1", shared + "2"], "justification": "test"}]
    assert overlap_keys([("git", "add")], rules) == {("git add", shared + "1"), ("git add", shared + "2")}
