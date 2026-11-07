"""Mutation testing runs on a copy of the tree; the options that mutate the working tree itself stay forbidden."""

import pytest

from tests.runtime import load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "command",
    [
        "cargo mutants --in-place",
        "cargo mutants --file src/lib.rs --in-place",
        "pnpm exec stryker run --inPlace",
        "pnpm exec stryker run --mutate src/a.ts --inPlace",
        "uv run --frozen mutmut apply 1",
    ],
)
def test_mutation_testing_may_not_write_mutants_into_the_working_tree(command: str) -> None:
    assert guard.check("forbidden", {"tool_input": {"command": command}}) == 2


@pytest.mark.parametrize(
    "command",
    ["cargo mutants --file src/lib.rs", "pnpm exec stryker run --mutate src/a.ts", "uv run --frozen mutmut run"],
)
def test_mutation_testing_on_a_copy_is_not_forbidden(command: str) -> None:
    assert guard.check("forbidden", {"tool_input": {"command": command}}) == 0
