"""The POSIX ERE to Z3 converter accepts exactly the strings the system grep accepts (P2 and P3 of #73)."""

from functools import cache
import json

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from tests.ere_to_z3 import UnsupportedPattern, matches, witness
from tests.runtime import REPO_ROOT, load_script_module


command_policy = load_script_module("agents/hooks/guard_command.py", "guard_command").command_policy
FORBIDDEN = json.loads((REPO_ROOT / "agents/hooks/rules/forbidden_commands.json").read_text())["rules"]
REAL_PATTERNS = [pattern for rule in FORBIDDEN for pattern in rule["patterns"]]


@pytest.mark.parametrize(
    ("pattern", "accepted", "rejected"),
    [
        pytest.param("abc", ["abc", "xabcx"], ["ab", "acb", ""], id="literal is searched anywhere"),
        pytest.param("^abc", ["abc", "abcd"], ["xabc"], id="start anchor"),
        pytest.param("abc$", ["abc", "xabc"], ["abcx"], id="end anchor"),
        pytest.param("^abc$", ["abc"], ["abcd", "xabc", ""], id="both anchors"),
        pytest.param("^$", [""], ["a"], id="empty line"),
        pytest.param("a|b", ["a", "b", "xbx"], ["c", ""], id="alternation"),
        pytest.param("^(a|b)c", ["ac", "bcd"], ["cc", "xac"], id="group alternation"),
        pytest.param("(^|x)a", ["a", "xa", "zxa"], ["za"], id="anchor inside a group"),
        pytest.param("ab*c", ["ac", "abbc"], ["abxc"], id="star"),
        pytest.param("ab+c", ["abc", "abbc"], ["ac"], id="plus"),
        pytest.param("ab?c", ["ac", "abc"], ["abbc"], id="option"),
        pytest.param("^a{2,3}$", ["aa", "aaa"], ["a", "aaaa"], id="bounded repetition"),
        pytest.param("^a{2}$", ["aa"], ["a", "aaa"], id="exact repetition"),
        pytest.param("^a{2,}$", ["aa", "aaaa"], ["a"], id="open repetition"),
        pytest.param("^a.c$", ["abc", "a c"], ["ac", "abbc"], id="any character"),
        pytest.param("^[abc]+$", ["abca"], ["abd", ""], id="bracket set"),
        pytest.param("^[a-c]$", ["b"], ["d", "-"], id="bracket range"),
        pytest.param("^[^a-c]$", ["d", " "], ["a", "bb"], id="negated bracket"),
        pytest.param("^[a-]$", ["a", "-"], ["b"], id="trailing dash is literal"),
        pytest.param("^[-A]$", ["-", "A"], ["/", "B", "."], id="leading dash is literal"),
        pytest.param("^a\x01$", ["a\x01"], ["a", "a\x02"], id="start of heading is an ordinary character"),
        pytest.param("^a\x02$", ["a\x02"], ["a"], id="the former sentinel is an ordinary character"),
        pytest.param("^[]a]$", ["]", "a"], ["b"], id="leading bracket is literal"),
        pytest.param("^[[:space:]]$", [" ", "\t"], ["a"], id="space class"),
        pytest.param("^[^[:space:]]*$", ["abc", ""], ["a b"], id="negated class"),
        pytest.param(r"^a\.b$", ["a.b"], ["axb"], id="escaped dot"),
        pytest.param(r"^a\$$", ["a$"], ["a"], id="escaped dollar"),
        pytest.param("^[[:digit:]]+$", ["0", "42"], ["a", "", "4a"], id="digit class"),
        pytest.param("ターミナル", ["xターミナルx"], ["ターミ"], id="non ASCII literal"),
    ],
)
def test_the_converted_pattern_accepts_and_rejects_like_grep(
    pattern: str, accepted: list[str], rejected: list[str]
) -> None:
    for text in accepted:
        assert matches(pattern, text), text
    for text in rejected:
        assert not matches(pattern, text), text


@pytest.mark.parametrize(("pattern", "text"), [("^abc$", "ABC"), ("[a-c]x", "BX")])
def test_ignoring_case_folds_literals_and_bracket_sets(pattern: str, text: str) -> None:
    assert matches(pattern, text, ignore_case=True)
    assert not matches(pattern, text, ignore_case=False)


def test_ignoring_case_also_folds_what_a_negated_bracket_excludes() -> None:
    assert matches("^[^a]$", "A", ignore_case=False)
    assert not matches("^[^a]$", "A", ignore_case=True)


@pytest.mark.parametrize(
    "pattern",
    [r"\1", r"(a)\1", r"\w", "(?=a)", "[[:bogus:]]", "(a", "a)", "[a", "a{2", "*a", r"[\.]", r"[a\]]"]
    + [r"\<a", r"a\>", r"\`a", r"a\'"]
    + ["[[:alpha:]]", "[[:alnum:]]", "[[:upper:]]", "[[:lower:]]"],
)
def test_syntax_outside_the_rule_dialect_is_refused(pattern: str) -> None:
    with pytest.raises(UnsupportedPattern):
        matches(pattern, "a")


ALPHABET = list("abcdeghimnoprstuvwxyz0123456789 \t-./=:_")
FRAGMENTS = [
    "git add",
    "git commit",
    " --no-verify",
    " -n",
    " -A",
    ".venv/bin/python",
    "find . -delete",
    "herdr agent start",
    " -- ",
    "cargo mutants",
    "--in-place",
    "file:",
    "Terminal",
    "python3 -m pip",
]
TEXTS = st.lists(st.one_of(st.text(alphabet=ALPHABET, max_size=6), st.sampled_from(FRAGMENTS)), max_size=6).map(
    "".join
)


@pytest.mark.parametrize("pattern", ["a^b", "a$b", "^a$b", "a{2}^"])
def test_a_pattern_no_line_can_satisfy_has_no_witness(pattern: str) -> None:
    assert witness(pattern) is None


@cache
def fixed_witness(pattern: str, ignore_case: bool) -> str:
    """One witness per pattern: Z3 may answer differently on each call, which would make generation flaky."""
    return witness(pattern, ignore_case) or ""


@st.composite
def near_witnesses(draw: st.DrawFn, pattern: str, ignore_case: bool) -> str:
    """A line the pattern occurs in, edited a little, so both sides of its boundary are compared."""
    line = fixed_witness(pattern, ignore_case)
    for _ in range(draw(st.integers(0, 2))):
        index = draw(st.integers(0, len(line)))
        character = draw(st.sampled_from(ALPHABET))
        edit = draw(st.sampled_from(["insert", "replace", "delete"]))
        line = {
            "insert": line[:index] + character + line[index:],
            "replace": line[:index] + character + line[index + 1 :],
            "delete": line[:index] + line[index + 1 :],
        }[edit]
    return line


@pytest.mark.parametrize("pattern", REAL_PATTERNS)
@pytest.mark.parametrize("ignore_case", [False, True])
@settings(
    max_examples=40, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(data=st.data())
def test_every_forbidden_pattern_agrees_with_grep_near_its_boundary(
    pattern: str, ignore_case: bool, data: st.DataObject
) -> None:
    line = data.draw(near_witnesses(pattern, ignore_case))
    expected = command_policy.regex_matches(pattern, line, insensitive=ignore_case)
    assert matches(pattern, line, ignore_case=ignore_case) == expected, line


@pytest.mark.parametrize("pattern", REAL_PATTERNS)
def test_a_witness_of_every_forbidden_pattern_is_matched_by_grep(pattern: str) -> None:
    line = witness(pattern)
    assert line is not None
    assert command_policy.regex_matches(pattern, line), line


@pytest.mark.parametrize("pattern", REAL_PATTERNS)
@pytest.mark.parametrize("ignore_case", [False, True])
@settings(
    max_examples=60, deadline=None, derandomize=True, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(text=TEXTS)
def test_every_forbidden_pattern_converts_to_what_grep_accepts(pattern: str, ignore_case: bool, text: str) -> None:
    expected = command_policy.regex_matches(pattern, text, insensitive=ignore_case)
    assert matches(pattern, text, ignore_case=ignore_case) == expected, text
