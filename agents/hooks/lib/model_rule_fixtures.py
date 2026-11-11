"""The eval fixtures of the model rules: planted code the rules are tested on, not code the repository runs."""

from pathlib import PurePosixPath

# The fixtures hold violations on purpose, so judging them would only report what they are for, and they belong to no
# language project, so no test run applies to them.
_FIXTURES = "agents/hooks/lint/model-rules/**/fixtures/**"


def is_model_rule_fixture(path: str) -> bool:
    """Whether the repository-relative POSIX `path` is a file inside a `fixtures` directory of the model rules."""
    return PurePosixPath(path).full_match(_FIXTURES)
