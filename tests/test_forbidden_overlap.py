"""P2: each allow prefix that is wider than a forbidden regex's carve-out is on a reviewed list.

An overlap is not a defect by itself: the provider allows the prefix and the hook denies the narrower
form, as for `git add` and `git add .`. The list below was reviewed for #73; a prefix that newly overlaps
a forbidden form, or one that stops overlapping because a rule was deleted, changes it and fails here.
"""

import json
import sys

from tests.rule_overlap import COMMAND_LOOKUP, find_overlaps
from tests.runtime import REPO_ROOT


sys.path.insert(0, str(REPO_ROOT / "agents/hooks/lib"))

from shell_wrappers import COMMAND_LOOKUP as GUARD_COMMAND_LOOKUP, WRAPPERS


POLICY = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
FORBIDDEN = json.loads((REPO_ROOT / "agents/hooks/rules/forbidden_commands.json").read_text())["rules"]
ALLOW = [tuple(rule["prefix"]) for rule in POLICY if rule["decision"] == "allow"]

GIT_ADD = (
    r"git[[:space:]]+add([[:space:]]+-[^[:space:]]*)*[[:space:]]+(\./?|-[A-Za-z]*A[A-Za-z]*|--all)([[:space:]]|$)"
)
GIT_COMMIT = (
    r"git[[:space:]]+commit([[:space:]].*)?[[:space:]]+(--no-veri[a-z]*|-[aeiopqsvz]*n[^[:space:]]*)([[:space:]]|$)"
)
PIP = r"(^|[[:space:]])python[0-9.]*([[:space:]]+(-[A-Za-z]*[WX]([^[:space:]]+|[[:space:]]+[^[:space:]]+)|--check-hash-based-pycs[[:space:]]+[^[:space:]]+|-[A-Za-z]+))*[[:space:]]+-[A-Za-z]*m[[:space:]]*(pip|ensurepip)([[:space:]]|$)"
FIND = r"(^|[[:space:]])find[[:space:]].*[[:space:]]-(delete|exec|execdir|ok|okdir|fprint|fprint0|fprintf|fls)([[:space:]]|$)"
HERDR = r"^herdr[[:space:]]+agent[[:space:]]+start([[:space:]].*)?[[:space:]]--([[:space:]]|$)"
CARGO = "^cargo mutants .*--in-place"
MUTMUT = "^uv run .*mutmut apply"
STRYKER = "^pnpm exec stryker .*--inPlace"
VENV_PYTHON = r"(^|[[:space:]])([^[:space:]]*/)?\.venv/bin/python([0-9.]*)?([[:space:]]|$)"
BROWSER_URL = "(^|[^a-z0-9+.-])(file|chrome):"
DESKTOP_APP = (
    "(^|[ =/.])(ghostty|terminal|iterm2?|warp(-stable)?|alacritty|kitty|wezterm(-gui)?|hyper|tabby"
    "|system[[:space:]]+(settings|preferences)|systempreferences|keychain[[:space:]]+access|keychainaccess"
    "|passwords|1password|onepassword[0-9]*|script[[:space:]]+editor|scripteditor2?|automator|shortcuts"
    "|ターミナル|システム設定|システム環境設定|キーチェーンアクセス|パスワード|スクリプトエディタ|ショートカット)"
    r"(\.app)?([ /:]|$)"
)

# (allow prefix, the whole forbidden pattern it overlaps)
# `xargs` meets every rule: the hooks unwrap it and deny the inner command, as for `git add` and `git add .`.
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
    ("xargs", VENV_PYTHON),
    ("xargs", "^" + GIT_ADD),
    ("xargs", "(^|[[:space:]])" + GIT_ADD),
    ("xargs", "^" + GIT_COMMIT),
    ("xargs", "(^|[[:space:]])" + GIT_COMMIT),
    ("xargs", PIP),
    ("xargs", FIND),
    ("xargs", HERDR),
    ("xargs", CARGO),
    ("xargs", STRYKER),
    ("xargs", MUTMUT),
    ("xargs", BROWSER_URL),
    ("xargs", DESKTOP_APP),
}


def overlap_keys(prefixes: list[tuple[str, ...]], rules: list[dict]) -> set[tuple[str, str]]:
    return {(" ".join(item.prefix), item.pattern) for item in find_overlaps(prefixes, rules, wrappers=WRAPPERS)}


def test_the_overlaps_between_allow_prefixes_and_forbidden_rules_are_the_reviewed_ones() -> None:
    found = overlap_keys(ALLOW, FORBIDDEN)
    assert (found - REVIEWED, REVIEWED - found) == (set(), set())


def test_a_widened_allow_prefix_changes_the_overlaps() -> None:
    assert overlap_keys([*ALLOW, ("git",)], FORBIDDEN) != REVIEWED


def test_a_deleted_forbidden_rule_changes_the_overlaps() -> None:
    assert overlap_keys(ALLOW, FORBIDDEN[1:]) != REVIEWED


def test_an_allowed_wrapper_overlaps_the_scoped_rule_of_the_command_it_runs() -> None:
    rules = [{"programs": ["uv"], "patterns": [MUTMUT], "justification": "test"}]
    found = find_overlaps([("xargs",)], rules, wrappers=WRAPPERS)
    assert [(item.prefix, item.pattern) for item in found] == [(("xargs",), MUTMUT)]
    assert found[0].witness.lower().startswith("xargs uv run ")


def test_a_wrapper_overlap_needs_the_inner_program_the_rule_governs() -> None:
    rules = [{"programs": ["uv"], "patterns": ["^git add"], "justification": "test"}]
    assert find_overlaps([("xargs", "-0")], rules, wrappers=WRAPPERS) == ()


def test_a_wrapper_overlap_honors_the_exceptions_of_the_rule() -> None:
    rules = [{"programs": ["uv"], "patterns": [MUTMUT], "exceptions": ["mutmut apply"], "justification": "test"}]
    assert find_overlaps([("xargs",)], rules, wrappers=WRAPPERS) == ()


def test_command_lookup_does_not_run_the_command_so_it_overlaps_nothing() -> None:
    rules = [{"programs": ["uv"], "patterns": [MUTMUT], "justification": "test"}]
    assert find_overlaps([("command", "-v"), ("command", "-V")], rules, wrappers=WRAPPERS) == ()


def test_the_command_lookup_options_match_the_guard() -> None:
    assert COMMAND_LOOKUP == GUARD_COMMAND_LOOKUP


def test_a_wrapper_is_unwrapped_only_when_the_caller_names_it() -> None:
    rules = [{"programs": ["uv"], "patterns": [MUTMUT], "justification": "test"}]
    assert find_overlaps([("xargs",)], rules) == ()


def test_patterns_that_share_a_long_start_are_distinct_overlaps() -> None:
    shared = "^git add " + "x" * 60
    rules = [{"patterns": [shared + "1", shared + "2"], "justification": "test"}]
    assert overlap_keys([("git", "add")], rules) == {("git add", shared + "1"), ("git add", shared + "2")}
