"""P3 of #73: two sets of forbidden regex rules deny the same lines, or Z3 names a line they split on."""

import json

import pytest

from tests.denial_difference import Difference, find_denial_difference
from tests.runtime import CliRunner, REPO_ROOT


NO_VERIFY = {"patterns": ["^git commit .*--no-verify"], "justification": "test"}
GUARDED = {
    "patterns": ["^herdr agent start .* -- "],
    "exceptions": ["^herdr agent start x -- $"],
    "justification": "test",
}
SCOPED = {"programs": ["cargo"], "patterns": ["^cargo mutants .*--in-place"], "justification": "test"}


def test_identical_rule_sets_do_not_differ() -> None:
    assert find_denial_difference([NO_VERIFY, GUARDED, SCOPED], [NO_VERIFY, GUARDED, SCOPED]) is None


def test_the_order_and_grouping_of_rules_do_not_matter() -> None:
    split = [{**NO_VERIFY, "patterns": [pattern]} for pattern in ["^git commit .*--no-verify", "^git commit -n"]]
    merged = [{**NO_VERIFY, "patterns": ["^git commit -n", "^git commit .*--no-verify"]}]
    assert find_denial_difference(split, merged) is None


def test_a_dropped_pattern_is_a_line_only_the_source_denies() -> None:
    difference = find_denial_difference([NO_VERIFY, SCOPED], [SCOPED])
    assert difference is not None
    assert difference.denied_by == "source"
    assert difference.line.startswith("git commit ")


def test_a_dropped_exception_is_a_line_only_the_generated_rules_deny() -> None:
    difference = find_denial_difference([GUARDED], [{**GUARDED, "exceptions": []}])
    assert difference == Difference("herdr agent start x -- ", "generated")


def test_a_dropped_program_scope_widens_the_rule_to_every_program() -> None:
    caseless = {"programs": ["cargo"], "patterns": ["^[0-9]*cargo"], "justification": "test"}
    unscoped = {key: value for key, value in caseless.items() if key != "programs"}
    difference = find_denial_difference([caseless], [unscoped])
    assert difference is not None
    assert difference.denied_by == "generated"
    assert difference.line.split(" ")[0] != "cargo"


def test_a_dropped_program_scope_also_drops_the_case_folding_the_scope_brings() -> None:
    unscoped = {key: value for key, value in SCOPED.items() if key != "programs"}
    difference = find_denial_difference([SCOPED], [unscoped])
    assert difference is not None
    assert difference.denied_by == "source"
    assert difference.line != difference.line.lower()


def test_no_rules_deny_nothing() -> None:
    assert find_denial_difference([], []) is None
    assert find_denial_difference([NO_VERIFY], []) is not None


def test_a_scoped_rule_ignores_case_in_its_patterns() -> None:
    upper = {**SCOPED, "patterns": ["^CARGO MUTANTS .*--IN-PLACE"]}
    assert find_denial_difference([SCOPED], [upper]) is None


FORBIDDEN = json.loads((REPO_ROOT / "agents/hooks/rules/forbidden_commands.json").read_text())["rules"]


@pytest.mark.parametrize("index", range(len(FORBIDDEN)))
def test_dropping_any_real_rule_is_found(index: int) -> None:
    difference = find_denial_difference([FORBIDDEN[index]], [])
    assert difference is not None
    assert difference.denied_by == "source"


SOURCE_RULES = [pytest.param(rule, id=f"rule {index}") for index, rule in enumerate(FORBIDDEN)]


@pytest.fixture(scope="module")
def generated_forbidden(agent_harness: CliRunner, tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    path = tmp_path_factory.mktemp("forbidden") / "forbidden_commands.json"
    agent_harness("generate-forbidden-commands", "--output", str(path))
    return json.loads(path.read_text())["rules"]


def generated_rule_for(source: dict, generated: list[dict]) -> dict:
    """The generated rule with the source rule's patterns; the order and grouping of rules are not compared."""
    found = [rule for rule in generated if frozenset(rule["patterns"]) == frozenset(source["patterns"])]
    assert len(found) == 1, f"expected one generated rule for {source['patterns']}"
    return found[0]


@pytest.mark.integration
def test_the_generated_forbidden_rules_are_as_many_as_the_source(generated_forbidden: list[dict]) -> None:
    assert len(generated_forbidden) == len(FORBIDDEN)


@pytest.mark.integration
@pytest.mark.parametrize("source", [pytest.param(rule, id=f"rule {index}") for index, rule in enumerate(FORBIDDEN)])
def test_a_generated_forbidden_rule_is_its_source_rule(source: dict, generated_forbidden: list[dict]) -> None:
    assert generated_rule_for(source, generated_forbidden) == source


@pytest.mark.integration
@pytest.mark.parametrize("source", SOURCE_RULES)
def test_a_generated_forbidden_rule_denies_the_lines_its_source_rule_denies(
    source: dict, generated_forbidden: list[dict]
) -> None:
    assert find_denial_difference([source], [generated_rule_for(source, generated_forbidden)]) is None
