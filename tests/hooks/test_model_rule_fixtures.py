"""The eval fixtures of the model rules are one concept with one definition shared by every hook that skips them."""

import pytest
from tests.runtime import load_script_module

fixtures = load_script_module("agents/hooks/lib/model_rule_fixtures.py", "model_rule_fixtures")


@pytest.mark.parametrize(
    "path",
    [
        "agents/hooks/lint/model-rules/python/m-05/fixtures/bad.py",
        "agents/hooks/lint/model-rules/python/fixtures/bad.py",
        "agents/hooks/lint/model-rules/go/m-05/fixtures/nested/deeper/bad.go",
        "agents/hooks/lint/model-rules/rust/m-60/fixtures/good/ok.rs",
    ],
)
def test_files_under_a_fixtures_directory_of_the_model_rules_are_fixtures(path: str) -> None:
    assert fixtures.is_model_rule_fixture(path)


@pytest.mark.parametrize(
    "path",
    [
        "tests/fixtures/data.txt",
        "agents/hooks/lint/fixtures/bad.py",
        "agents/hooks/lint/model-rules/go/m-05/helper.go",
        "agents/hooks/lint/model-rules/go/m-05/rule.md",
        "agents/hooks/lint/model-rules/go/m-05/fixtures",
        "other/agents/hooks/lint/model-rules/go/m-05/fixtures/bad.go",
    ],
)
def test_other_paths_are_not_fixtures(path: str) -> None:
    assert not fixtures.is_model_rule_fixture(path)
