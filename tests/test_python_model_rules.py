"""The python-style model rules select the subjects they ask about; the model itself is not asked."""

from pathlib import Path

import pytest

from tests.test_model_rule_files import RULE_IDS, plan, repository, subjects_by_rule  # noqa: F401 (fixture)

pytestmark = pytest.mark.needs_jev_lint

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


def env():
    return os.environ.get("SOME_HOME_DIR")


@pytest.fixture
def one():
    return 1


@fixture
def two():
    return 2


@pytest_fixture
def three():
    return 3


def parse(raw):
    return Money.model_validate(json.loads(raw))


class FrozenBaseModel(pydantic.BaseModel):
    pass


class Locked(FrozenBase, strict=False):
    pass


class Plain:
    def __init__(self, name):
        self.name = name


def test_a(one):
    assert one == 1


def test_b(one):
    assert one == 2
"""


def test_python_style_model_rules_select_the_subjects_they_ask_about(repository: Path) -> None:  # noqa: F811
    (repository / "sample.py").write_text(PYTHON_STYLE_SOURCE)

    counts = subjects_by_rule(plan(repository))

    # `Age` and `Money` are value-object candidates (a dataclass and a pydantic model, written qualified); `Token`
    # has another base. `make_age` is a constructor by name. Only `mode` compares a string literal, and `env` looks one
    # up by key; plain strings in `label` and `say`, and a docstring (`only_doc`), are not subjects. `pytest.fixture`,
    # the bare `@fixture` and an aliased `@pytest_fixture` all select a fixture. The module has test functions, so
    # the parametrize rule asks
    # about it. The aliased import is asked about. `parse` is the only `model_validate` call, and `Plain` the only
    # class with an `__init__`; `Locked` is the only class with class keywords, and
    # `FrozenBaseModel` (also a pydantic model, so a third value-object candidate) is the one asked about its settings.
    assert {rule: n for rule, n in counts.items() if rule not in RULE_IDS} == {
        "value-object-is-immutable": 3,
        "construction-placement-by-purity": 1,
        "fixed-choices-use-enum": 1,
        "string-literal-is-named-constant": 2,
        "fixture-justified": 3,
        "repeated-tests-use-parametrize": 1,
        "import-name-self-explanatory": 1,
        "json-parse-uses-model-validate-json": 1,
        "plain-class-defines-slots": 1,
        "frozen-model-subclass-keeps-locked-settings": 1,
        "frozen-base-model-sets-all-settings": 1,
    }


def subjects_of(repository: Path, rule: str, source: str) -> int:  # noqa: F811
    """How many subjects one rule selects in a sample module, counting the rules that select everything too."""
    (repository / "sample.py").write_text(source)
    return sum(entry["subjects"] for entry in plan(repository)["byRule"] if entry["rule"] == rule)


def test_demeter_rule_selects_a_chain_of_property_reads(repository: Path) -> None:  # noqa: F811
    source = """\
def city(order):
    return order.customer.address.city


def street(user):
    return user.address.street
"""

    # Three member accesses reach through collaborators even when no call ends the chain; two do not.
    assert subjects_of(repository, "no-reaching-through-collaborators", source) == 1


def test_mutable_collection_rule_selects_a_returned_public_field(repository: Path) -> None:  # noqa: F811
    source = """\
class Cart:
    def __init__(self):
        self.items = []

    def contents(self):
        return self.items

    def size(self):
        return len(self.items)
"""

    # A public field handed out as it is can be the mutable collection; a value computed from it cannot.
    assert subjects_of(repository, "no-exposed-mutable-collection", source) == 1


def test_comment_rule_selects_a_comment_placed_just_before_a_function(repository: Path) -> None:  # noqa: F811
    source = """\
# Return the name of the user.
def name(user):
    return user.name


# Cache the total.
@cache
def total(items):
    return sum(items)


# noqa: D103
def age(user):
    return user.age


def email(user):
    return user.email
"""

    # A comment above a function or its decorators can restate it as much as one inside; a tool directive cannot.
    assert subjects_of(repository, "no-comment-restating-code", source) == 2
