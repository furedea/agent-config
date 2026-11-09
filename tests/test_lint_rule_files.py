"""Contract of the rule files under agents/lint/rules: each parses, sits where it declares, and cites a live source."""

from pathlib import Path

import pytest

from agents.lint.registry import Method, source_problem
from tests.lint_registry import load_registry, load_rule, rule_files
from tests.runtime import REPO_ROOT

RULE_FILES = rule_files()


def test_the_registry_has_rule_files_of_the_seeded_methods() -> None:
    methods = {rule.method for rule in load_registry()}

    assert {Method.LINTER, Method.AST_GREP, Method.PROSE} <= methods


def test_rule_ids_are_unique_across_the_files() -> None:
    assert len(list(load_registry())) == len(RULE_FILES)


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda path: path.name)
def test_a_rule_file_sits_in_its_language_directory(path: Path) -> None:
    assert path.parent.name == load_rule(path).language


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda path: path.name)
def test_a_rule_file_is_named_after_its_id(path: Path) -> None:
    assert path.stem == load_rule(path).id.replace("-", "_")


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda path: path.name)
def test_a_rule_cites_a_source_line_that_still_states_it(path: Path) -> None:
    assert source_problem(load_rule(path).source, REPO_ROOT) is None
