"""The python-style model rules select the subjects they ask about; the model itself is not asked."""

import shutil
from pathlib import Path

import pytest

from tests.test_model_rule_files import RULE_IDS, plan, repository, subjects_by_rule  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(shutil.which("jev-lint") is None, reason="jev-lint is not on PATH")

PYTHON_STYLE_SOURCE = """\
import pydantic
import pytest
from os import path as p


@dataclass
class Age:
    value: int


class Money(pydantic.BaseModel):
    amount: int


class Token(Base):
    pass


def make_age(data):
    return Age(data["v"])


def mode(kind):
    if kind == "fast":
        return 1
    return 0


def label():
    \"\"\"Docstring only.\"\"\"
    return "a meaningful label"


def only_doc():
    \"\"\"Only a docstring.\"\"\"


def say():
    print("hello world")


@pytest.fixture
def one():
    return 1


@fixture
def two():
    return 2


@pytest_fixture
def three():
    return 3


def test_a(one):
    assert one == 1


def test_b(one):
    assert one == 2
"""


def test_python_style_model_rules_select_the_subjects_they_ask_about(repository: Path) -> None:  # noqa: F811
    (repository / "sample.py").write_text(PYTHON_STYLE_SOURCE)

    counts = subjects_by_rule(plan(repository))

    # `Age` and `Money` are value-object candidates (a dataclass and a pydantic model, written qualified); `Token`
    # has another base. `make_age` is a constructor by name. Only `mode` compares a string literal, and the strings
    # in `label` and `say` count but a docstring does not (`only_doc`). `pytest.fixture`, the bare `@fixture` and an
    # aliased `@pytest_fixture` all select a fixture. The module has test functions, so the parametrize rule asks
    # about it. The aliased import is asked about.
    assert {rule: n for rule, n in counts.items() if rule not in RULE_IDS} == {
        "value-object-is-immutable": 2,
        "construction-placement-by-purity": 1,
        "fixed-choices-use-enum": 1,
        "string-literal-is-named-constant": 3,
        "fixture-justified": 3,
        "repeated-tests-use-parametrize": 1,
        "import-name-self-explanatory": 1,
    }
