"""Only a simple function body is judged command by command; any other body asks, as every function did before."""

import pytest
from hook_decision import Verdict
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


def decide(kind: str, command: str) -> Verdict:
    return guard.decide(kind, {"tool_input": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [
        "f(){ cat <<'EOF'\nhi\nEOF\n}; f",
        "f(){ cat <<EOF\n$1\nEOF\n}; f x",
        "outer(){ inner(){ echo hi; }; inner; }; outer",
        "f(){ unset x; }; f",
        "f(){ eval echo hi; }; f",
        "f(){ trap 'echo hi' EXIT; }; f",
        "f(){ let x=1; }; f",
        "f(){ (( x = 1 )); }; f",
        "f(){ echo $(( 1 + 1 )); }; f",
        "f(){ [[ 1 -eq 1 ]]; }; f",
        'f(){ echo "${a[0]}"; }; f',
        'f(){ echo "${x:0:1}"; }; f',
        "f(){ a[0]=x; }; f",
        "f(){ x+=y; }; f",
        "f(){ source ./x.sh; }; f",
        "f(){ . ./x.sh; }; f",
        "f(){ alias g=echo; }; f",
        "f(){ builtin echo hi; }; f",
        "f(){ command echo hi; }; f",
        "f(){ hash -r; }; f",
        "f(){ printf -v x %s hi; }; f",
        "f(){ read -r x; }; f",
        "f(){ mapfile -t a; }; f",
        "f(){ local -r x=1; }; f",
        'f(){ local "x$1=1"; }; f y',
        "f(){ export x=1; }; f",
        "f(){ readonly x=1; }; f",
        "f(){ declare x=1; }; f",
        "f(){ sh <<'EOF'\necho hi\nEOF\n}; f",
        "f(){ . ./script.sh; }; f",
        'f(){ builtin shift; find . "$1"; }; f x -delete',
        'f(){ command shift; find . "$1"; }; f x -delete',
        'f(){ noglob shift; find . "$1"; }; f x -delete',
        "f(){ trap 'echo done' EXIT; echo hi; }; f",
    ],
)
def test_a_body_using_what_evaluates_text_again_asks(command: str) -> None:
    assert decide("allowed", command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "declare -a a; f(){ unset \"$1\"; }; f 'a[$(find . -delete)0]'",
        "declare -a a; f(){ [[ -v \"$1\" ]]; }; f 'a[$(find . -delete)0]'",
        "declare -a a; f(){ [[ -R \"$1\" ]]; }; f 'a[$(find . -delete)0]'",
        "declare -a a; f(){ test -v \"$1\"; }; f 'a[$(find . -delete)0]'",
        "declare -a a; f(){ [ -v \"$1\" ]; }; f 'a[$(find . -delete)0]'",
        "f(){ cat <<EOF\nx\nEOF\n}; eval 'f; git commit --no-verify -m x'",
    ],
)
def test_the_forms_the_review_found_no_longer_pass(kind: str, command: str) -> None:
    assert decide(kind, command).decision != "allow"


def test_a_nested_definition_asks_instead_of_denying_with_the_outer_arguments() -> None:
    command = 'outer(){ inner(){ find . "$1"; }; inner; }; outer -delete'
    assert decide("forbidden", command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        'f(){ local id=$1; mkdir -p "$id"; }; f x',
        'f(){ [[ -n "$1" ]] && echo "$1"; }; f x',
        'f(){ for x in a b; do echo "$x"; done; }; f',
        "f(){ if [ -d x ]; then echo y; fi; }; f",
        't(){ printf "%s\\n" "$@" | sort; }; t b a',
        "f(){ case $1 in a) echo a;; esac; }; f a",
    ],
)
def test_a_simple_body_is_judged_command_by_command(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


def test_a_simple_body_still_denies_what_a_caller_hands_it() -> None:
    assert decide("forbidden", 'f(){ find . "$1"; }; f -delete').decision == "deny"
