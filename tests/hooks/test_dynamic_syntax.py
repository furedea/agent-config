"""Shell functions, loops, and substitutions run unprompted unless a program with external effect hides in them."""

import pytest
from hook_decision import Verdict
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
git_guard = load_script_module("agents/hooks/guard_git.py", "guard_git")
pytestmark = pytest.mark.usefixtures("isolated_project")

# Two function definitions the guard asked for on 2026-11-14; the log truncated each after its first line.
RULE_WRITERS = [
    "cd agents/hooks/lint/model-rules/python && mk() { id=$1; mkdir -p $id; cat > $id/rule.yml; }\n"
    "mk no-bare-except <<'EOF'\nid: no-bare-except\nEOF",
    'cd agents/hooks/lint/model-rules/typescript && mk() { mkdir -p "$1"; cat > "$1/rule.yml"; }\n'
    "mk no-any <<'EOF'\nid: no-any\nEOF",
]


def decide(kind: str, command: str) -> Verdict:
    return guard.decide(kind, {"tool_input": {"command": command}})


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        *RULE_WRITERS,
        'f() { mkdir -p "$1"; }; f build',
        'function f { echo "$1"; }; f x',
        "f() ( cd build && make ); f",
        'for f in src/*.py; do ruff check "$f"; done',
        'while read -r line; do echo "$line"; done < list.txt',
        'echo "$(git rev-parse HEAD)"',
    ],
)
def test_functions_loops_and_substitutions_of_sandbox_local_programs_run_unprompted(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "f() { gh pr merge 1; }; f",
        'f() { gh api -X DELETE "$1"; }; f repos/o/r',
        'f() { gh pr comment "$@"; }; f 1 --body x',
        "f() { curl https://example.com; }; f",
        "f() { npx cowsay hi; }; f",
    ],
)
def test_a_program_with_external_effect_inside_a_function_is_judged_as_written(command: str) -> None:
    assert decide("allowed", command).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "CMD=gh; $CMD pr merge 1",
        '"$CMD" pr view 1',
        "${CMD:-gh} pr view 1",
        "$(echo gh) pr view 1",
        "`echo gh` pr view 1",
        'f() { "$@"; }; f gh pr merge 1',
        "f() { $1 pr merge 1; }; f gh",
        "for t in ruff mypy; do $t .; done",
        'env "$CMD" pr view 1',
        "nohup $CMD pr view 1",
        "./*.sh",
    ],
)
def test_a_program_known_only_at_run_time_asks(command: str) -> None:
    """The Git guard asks for every call whose program a rule cannot name, whatever that program is."""
    assert git_guard.inspect(command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        'f() { builtin eval "$1"; }; f "gh pr merge 1"',
        'set -- "gh pr merge 1"; builtin eval "$1"',
        'trap "$X" EXIT',
        'f() { trap "$1" EXIT; }; f "gh pr merge 1"',
        'alias x="$X"',
        'f() { alias x="$1"; }; f "gh pr merge 1"',
    ],
)
def test_text_that_the_shell_runs_as_code_asks_when_computed(kind: str, command: str) -> None:
    verdict = decide(kind, command)
    assert verdict.decision == "ask"
    assert "review" in verdict.reason


@pytest.mark.parametrize(
    "command",
    ["trap 'gh pr merge 1' EXIT", "alias m='gh pr merge 1'", "builtin eval 'gh pr merge 1'"],
)
def test_a_literal_trap_alias_or_eval_script_is_judged_as_a_script(command: str) -> None:
    assert decide("allowed", command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    ["trap 'echo \"$tmp\" >&2' EXIT", "trap - EXIT", "trap -p", "trap INT", "alias ll='ls -l'", "alias", "alias ll"],
)
def test_traps_and_aliases_of_sandbox_local_commands_run_unprompted(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


@pytest.mark.parametrize("command", ["trap 'gh pr merge 1'", "alias 'gh pr merge 1'"])
def test_a_trap_without_a_signal_or_an_alias_lookup_runs_no_text(command: str) -> None:
    assert decide("allowed", command).decision == "allow"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_eval_of_a_computed_script_still_asks(kind: str) -> None:
    command = 'for i in 0 1 2 3 4; do eval "echo \\"\\$GIT_CONFIG_KEY_$i\\"" | cut -c1-160; done'
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "f() { git commit --no-verify -m x; }; f",
        "f(){ git add -A; }",
        "function f { gh repo delete x --yes; }",
        "$X; git commit --no-verify -m x",
        'f() { "$@"; }; git commit --no-verify -m x',
        "trap 'git commit --no-verify -m x' EXIT",
        "alias c='git commit --no-verify -m x'",
        "builtin eval 'git commit --no-verify -m x'",
    ],
)
def test_denials_see_every_command_in_a_function_body_trap_alias_or_beside_a_computed_call(command: str) -> None:
    assert decide("forbidden", command).decision == "deny"
