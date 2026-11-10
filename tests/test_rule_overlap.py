"""P2 of #73: the overlap between an allow prefix and a forbidden regex is found, with a witness line."""

import pytest

from tests.ere_to_z3 import UnsupportedPattern
from tests.rule_overlap import Overlap, find_overlaps
from tests.runtime import load_script_module


command_policy = load_script_module("agents/hooks/lib/command_policy.py", "command_policy")

GIT_ADD = {"patterns": [r"^git[[:space:]]+add[[:space:]]+\.([[:space:]]|$)"], "justification": "test"}
NO_VERIFY = {"patterns": ["^git commit .*--no-verify"], "justification": "test"}
MUTANTS = {"programs": ["cargo"], "patterns": ["^cargo mutants .*--in-place"], "justification": "test"}


def keys(overlaps: tuple[Overlap, ...]) -> set[tuple[tuple[str, ...], str]]:
    return {(item.prefix, item.pattern) for item in overlaps}


def test_a_prefix_that_no_forbidden_line_starts_with_has_no_overlap() -> None:
    assert find_overlaps([("git", "status")], [GIT_ADD, NO_VERIFY]) == ()


def test_a_prefix_wider_than_a_forbidden_form_overlaps_it_with_a_witness() -> None:
    (overlap,) = find_overlaps([("git", "add")], [GIT_ADD])
    assert overlap.prefix == ("git", "add")
    assert overlap.pattern == GIT_ADD["patterns"][0]
    assert overlap.witness.startswith("git add")
    assert command_policy.regex_matches(overlap.pattern, overlap.witness)


UNANCHORED = {"patterns": ["(^|[[:space:]])git[[:space:]]+add"], "justification": "test"}


def test_a_forbidden_form_that_only_the_free_tail_could_hold_is_no_overlap() -> None:
    assert find_overlaps([("actionlint",)], [UNANCHORED]) == ()
    assert find_overlaps([("echo", "hi")], [UNANCHORED]) == ()


def test_a_forbidden_form_that_begins_inside_the_prefix_words_overlaps() -> None:
    assert find_overlaps([("git",)], [UNANCHORED]) != ()
    assert find_overlaps([("git", "add")], [UNANCHORED]) != ()


def test_a_prefix_is_a_whole_word_sequence_not_a_character_prefix() -> None:
    assert find_overlaps([("git", "ad")], [GIT_ADD]) == ()


def test_a_prefix_longer_than_the_forbidden_form_overlaps_when_the_form_can_follow() -> None:
    assert keys(find_overlaps([("git", "commit")], [NO_VERIFY])) == {(("git", "commit"), NO_VERIFY["patterns"][0])}
    assert find_overlaps([("git", "commit", "-m")], [NO_VERIFY]) != ()


def test_an_exception_that_covers_the_whole_pattern_removes_the_overlap() -> None:
    covered = {**GIT_ADD, "exceptions": ["^git"]}
    assert find_overlaps([("git", "add")], [covered]) == ()


def test_an_exception_leaves_the_lines_it_does_not_cover() -> None:
    (overlap,) = find_overlaps([("git", "add")], [{**GIT_ADD, "exceptions": ["^git add \\.$"]}])
    assert overlap.witness != "git add ."
    assert command_policy.regex_matches(overlap.pattern, overlap.witness)


def test_a_rule_scoped_to_programs_applies_only_to_a_prefix_of_that_program() -> None:
    assert find_overlaps([("go", "test")], [MUTANTS]) == ()
    assert keys(find_overlaps([("cargo", "mutants")], [MUTANTS])) == {(("cargo", "mutants"), MUTANTS["patterns"][0])}


def test_a_scoped_rule_ignores_case_as_the_guard_does() -> None:
    scoped = {"programs": ["cargo"], "patterns": ["^cargo MUTANTS"], "justification": "test"}
    (overlap,) = find_overlaps([("cargo", "mutants")], [scoped])
    assert command_policy.regex_matches(scoped["patterns"][0], overlap.witness, insensitive=True)
    unscoped = {"patterns": ["^cargo MUTANTS"], "justification": "test"}
    assert find_overlaps([("cargo", "mutants")], [unscoped]) == ()


def test_every_prefix_and_rule_pair_is_reported_once() -> None:
    found = find_overlaps([("git", "add"), ("git", "commit")], [GIT_ADD, NO_VERIFY])
    assert keys(found) == {
        (("git", "add"), GIT_ADD["patterns"][0]),
        (("git", "commit"), NO_VERIFY["patterns"][0]),
    }


@pytest.mark.parametrize("prefix", [("tool", "sub command"), ("tool\t", "x"), ("tool", "")])
def test_a_prefix_word_holding_whitespace_or_nothing_is_refused(prefix: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="prefix word"):
        find_overlaps([prefix], [GIT_ADD])


def test_a_witness_may_hold_start_of_heading() -> None:
    (overlap,) = find_overlaps([("echo",)], [{"patterns": ["^echo \x01$"], "justification": "test"}])
    assert overlap.witness == "echo \x01"


@pytest.mark.parametrize("pattern", [r"(a)\1", "(?=a)"])
def test_a_pattern_outside_the_rule_dialect_is_refused_instead_of_skipped(pattern: str) -> None:
    with pytest.raises(UnsupportedPattern):
        find_overlaps([("git", "add")], [{"patterns": [pattern], "justification": "test"}])
