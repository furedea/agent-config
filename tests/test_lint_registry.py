"""Contract of the lint rule registry schema: required fields per method, examples, and source links."""

import copy
from pathlib import Path

import pytest

from agents.lint.registry import Method, Registry, Rule, RuleError, Source, source_problem

LINTER: dict[str, object] = {
    "id": "py-type-hints",
    "source": {"file": "docs/style.md", "line": 2, "text": "Always include type hints"},
    "language": "python",
    "method": "linter",
    "code": "ANN201",
    "version": 1,
    "examples": {"conforming": ["def f() -> int: ..."], "violating": ["def f(): ..."]},
}


def rule_data(**changes: object) -> dict[str, object]:
    data = copy.deepcopy(LINTER)
    data.update(changes)
    return {key: value for key, value in data.items() if value is not None}


@pytest.mark.parametrize(
    ("method", "extra"),
    [
        ("linter", {"code": "ANN201"}),
        ("ast-grep", {"code": None}),
        ("prose", {"code": None}),
        ("model", {"code": None, "threshold": 0.8}),
    ],
)
def test_each_method_accepts_its_own_fields(method: str, extra: dict[str, object]) -> None:
    rule = Rule.from_mapping(rule_data(method=method, **extra))

    assert rule.method is Method(method)


@pytest.mark.parametrize("field", ["id", "source", "language", "method", "version", "examples"])
def test_a_missing_required_field_is_rejected(field: str) -> None:
    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(**{field: None}))


@pytest.mark.parametrize("method", ["linter", "ast-grep", "prose", "model"])
def test_an_unknown_field_is_rejected_for_every_method(method: str) -> None:
    with pytest.raises(RuleError, match="unknown fields: severity"):
        Rule.from_mapping(rule_data(method=method, code="ANN201", threshold=0.5, severity="high"))


def test_an_unknown_method_is_rejected() -> None:
    with pytest.raises(RuleError, match="method must be one of"):
        Rule.from_mapping(rule_data(method="regex"))


def test_a_linter_rule_names_the_linter_code() -> None:
    with pytest.raises(RuleError, match="requires code"):
        Rule.from_mapping(rule_data(code=None))


@pytest.mark.parametrize("method", ["ast-grep", "prose"])
def test_only_a_linter_rule_may_name_a_linter_code(method: str) -> None:
    with pytest.raises(RuleError, match="code is only allowed on linter rules"):
        Rule.from_mapping(rule_data(method=method))


def test_a_model_rule_requires_a_threshold() -> None:
    with pytest.raises(RuleError, match="requires threshold"):
        Rule.from_mapping(rule_data(method="model", code=None))


@pytest.mark.parametrize("method", ["linter", "ast-grep", "prose"])
def test_only_a_model_rule_may_have_a_threshold(method: str) -> None:
    with pytest.raises(RuleError, match="threshold is only allowed on model rules"):
        Rule.from_mapping(rule_data(method=method, code="ANN201" if method == "linter" else None, threshold=0.5))


@pytest.mark.parametrize("threshold", [0, -0.1, 1.5, "high", True])
def test_a_threshold_is_a_score_in_the_half_open_unit_interval(threshold: object) -> None:
    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(method="model", code=None, threshold=threshold))


def test_a_threshold_of_one_is_allowed() -> None:
    assert Rule.from_mapping(rule_data(method="model", code=None, threshold=1)).threshold == 1.0


@pytest.mark.parametrize("version", [0, -1, "1", 1.0, True])
def test_a_version_is_a_positive_integer(version: object) -> None:
    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(version=version))


@pytest.mark.parametrize("side", ["conforming", "violating"])
@pytest.mark.parametrize("snippets", [[], [" \n"], "def f(): ..."])
def test_each_side_of_the_examples_needs_a_real_example(side: str, snippets: object) -> None:
    examples = {"conforming": ["a"], "violating": ["b"]} | {side: snippets}

    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(examples=examples))


def test_the_examples_need_both_sides() -> None:
    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(examples={"conforming": ["a"]}))


@pytest.mark.parametrize(
    "source",
    [
        {"file": "/etc/passwd", "line": 1, "text": "x"},
        {"file": "../outside.md", "line": 1, "text": "x"},
        {"file": "docs/style.md", "line": 0, "text": "x"},
        {"file": "docs/style.md", "line": 1, "text": "  "},
        {"file": "docs/style.md", "line": 1},
        {"file": "docs/style.md", "line": 1, "text": "x", "url": "https://example.invalid"},
    ],
)
def test_a_source_must_be_a_relative_file_line_and_quote(source: dict[str, object]) -> None:
    with pytest.raises(RuleError):
        Rule.from_mapping(rule_data(source=source))


def test_rule_ids_are_unique_in_a_registry() -> None:
    rule = Rule.from_mapping(rule_data())

    with pytest.raises(RuleError, match="duplicate rule ids: py-type-hints"):
        Registry.from_rules([rule, rule])


def test_a_registry_lists_its_rules_in_order() -> None:
    first = Rule.from_mapping(rule_data())
    second = Rule.from_mapping(rule_data(id="py-other"))

    assert list(Registry.from_rules([first, second])) == [first, second]


@pytest.fixture
def style_file(tmp_path: Path) -> Source:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/style.md").write_text("# Style\n- Always   include type hints\n- Keep it small\n")
    return Source(file="docs/style.md", line=2, text="Always include type hints")


def test_a_source_that_still_quotes_the_rule_has_no_problem(style_file: Source, tmp_path: Path) -> None:
    assert source_problem(style_file, tmp_path) is None


def test_a_missing_source_file_is_a_problem(tmp_path: Path) -> None:
    source = Source(file="docs/gone.md", line=1, text="x")

    assert source_problem(source, tmp_path) == "docs/gone.md does not exist"


def test_a_line_past_the_end_of_the_file_is_a_problem(style_file: Source, tmp_path: Path) -> None:
    moved = Source(file=style_file.file, line=4, text=style_file.text)

    assert "has 3 lines" in (source_problem(moved, tmp_path) or "")


def test_a_quote_that_moved_to_another_line_is_a_problem(style_file: Source, tmp_path: Path) -> None:
    moved = Source(file=style_file.file, line=3, text=style_file.text)

    assert "docs/style.md:3 no longer contains" in (source_problem(moved, tmp_path) or "")


def test_a_reworded_rule_is_a_problem(style_file: Source, tmp_path: Path) -> None:
    reworded = Source(file=style_file.file, line=2, text="Always include type annotations")

    assert source_problem(reworded, tmp_path) is not None
