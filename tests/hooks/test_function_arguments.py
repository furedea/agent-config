"""Functions, eval, and trap ask wherever the arguments, input, or builtins they rely on cannot be followed."""

from pathlib import Path

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
        'f(){ builtin shift; find . "$1"; }; f x -delete',
        'f(){ noglob shift; find . "$1"; }; f x -delete',
        'f(){ find . "$1"; }; noglob f -delete',
        'f(){ find . "$1"; }; nocorrect f -delete',
        'f(){ find . "$1"; }; - f -delete',
        'f(){ s\\hift; find . "$1"; }; f x -delete',
        'f(){ "shift"; find . "$1"; }; f x -delete',
        'f(){ command shift; find . "$1"; }; f x -delete',
        "eval -- 'git commit --no-verify -m x'",
        'f(){ find . "$1"; }; f -delete',
        '__guard_code_text(){ find . "$1"; }; __guard_code_text -delete',
    ],
)
def test_denials_see_through_builtin_prefixes_and_eval_option_ends(command: str) -> None:
    assert decide("forbidden", command).decision == "deny"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        'f(){ builtin set -- -delete; find . "$1"; }; f',
        'f(){ command set -- -delete; find . "$1"; }; f',
        "f(){ eval 'set -- -delete'; find . \"$1\"; }; f",
        'f(){ eval shift; find . "$1"; }; f x -delete',
        'f(){ a=$1; b=$a; find . "$b"; }; f -delete',
        'f(){ id=$1; find . "$id"; id=$2; }; f -delete safe',
        'f(){ id=$1; g; find . "$id"; }; g(){ id=-delete; }; f safe',
        'f(){ id=$1; read -r id; find . "$id"; }; f safe',
        'f(){ for a in "$@"; do find . "$a"; done; }; f -delete',
        "f(){ cat; } < secret.txt; f",
        "f(){ echo x; } > out.txt; f",
        "echo(){ printf 'gh pr merge 1\\n'; }; echo hi | sh",
        "printf(){ echo 'gh pr merge 1'; }; printf x | sh",
        "cd(){ builtin cd nested; }; cd other; sh < script.sh",
        "eval sh <<'EOF'\ngit commit --no-verify -m x\nEOF",
        "( trap sh EXIT; : ) <<'EOF'\ngit commit --no-verify -m x\nEOF",
        "env 'BASH_FUNC_gh%%=() { curl https://example.com; }' bash -c 'gh pr list'",
        "export 'BASH_FUNC_ls%%=() { gh pr merge 1; }'",
        "printf -v I\\FS x; f(){ find . $1; }; f 'ax-delete'",
        "printf -v {I,}FS x; f(){ find . $1; }; f 'ax-delete'",
        "(( IFS = 1 )); f(){ find . $1; }; f 'a1-delete'",
        ". ./env.sh; f(){ find . $1; }; f 'ax-delete'",
        'function declare { find . "$@"; }; declare -delete',
        'let(){ find . "$@"; }; let -delete',
        'command_not_found_handle(){ shift; find . "$@"; }; nosuchcmd -delete',
        'command_not_found_handler(){ shift; find . "$@"; }; nosuchcmd -delete',
        'f(){ find . "$1"; }; x=-delete; f "$x"',
        'f(){ local -l id=$1; find . "$id"; }; f -DELETE',
        'f(){ declare -u id; id=$1; find . "$id"; }; f -delete',
        """f(){ sh -c 'find . "$1"' marker "$1"; }; f -delete""",
        """sh -c 'find . "$1"' marker -delete""",
        "sh -c 'find . $0' -delete",
        'shopt -s extdebug; f(){ find . "${BASH_ARGV[0]}"; }; f -delete',
        'f(){ find . "${BASH_ARGV[@]}"; }; f -delete',
        'f(){ i=1; find . "${!i}"; }; f -delete',
        'f(){ "s"et -- -delete; find . "$1"; }; f',
        'c=shift; f(){ $c; find . "$1"; }; f x -delete',
        'f(){ "$1"; find . "$2"; }; f shift x -delete',
        'f(){ noglob "$1"; find . "$2"; }; f shift x -delete',
        'f(){ "$1" "$2"; find . "$3"; }; f noglob shift x -delete',
        'f(){ "$1"; find . "$2"; }; f zparseopts x -delete',
        "eval ':\n}\nls(){ find . \"$1\"; }\ng(){\n:'; ls -delete",
        "eval ':;}; ls(){ find . \"$1\"; }; g(){ :'; ls -delete",
        "eval ':\n}\nsh\ng(){\n:' <<'EOF'\ngit commit --no-verify -m x\nEOF",
        """set -E; trap 'find . "$1"' ERR; f(){ false; }; f -delete""",
        """set -T; trap 'shift' DEBUG; f(){ find . "$1"; }; f x -delete""",
        """set -E; trap 'i=1; find . "${!i}"' ERR; f(){ false; }; f -delete""",
        """set -T; trap 'set -e -- -delete' DEBUG; f(){ find . "$1"; }; f x""",
        """set -T; trap 'argv=(-delete)' DEBUG; f(){ find . "$1"; }; f x""",
        'f(){ printf -v id %s "$1"; find . "$id"; }; f -delete',
        'f(){ read -r id <<< "$1"; find . "$id"; }; f -delete',
        'f(){ zparseopts -D -E x=o; find . "$1"; }; f -x -delete',
        'f(){ argv=(-delete); find . "$1"; }; f x',
        'f(){ read -A argv <<< -delete; find . "$1"; }; f x',
        'f(){ find . "$_"; }; f -delete',
        "eval 'f(){ find . \"$1\"; }'; f -delete",
        "trap 'f(){ find . \"$1\"; }' EXIT; f -delete",
        'f(){ . ./script.sh; find . "$1"; }; f',
        """sh -s - -delete <<'EOF'\nfind . "$1"\nEOF""",
        'f(){ local \\-l id=$1; find . "$id"; }; f -DELETE',
        """sh -s -- -delete <<'EOF'\nfind . "$1"\nEOF""",
        "printf -v $'I\\x46S' x; f(){ find . $1; }; f 'ax-delete'",
        "declare $'I\\x46S=x'; f(){ find . $1; }; f 'ax-delete'",
    ],
)
def test_forms_where_arguments_input_or_builtins_cannot_be_followed_ask(
    kind: str, command: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "nested").mkdir()
    (isolated_project / "nested/script.sh").write_text("git commit --no-verify -m x\n")
    assert decide(kind, command).decision != "allow"


def test_a_function_reading_its_argument_through_a_redirection_is_judged_with_the_argument() -> None:
    command = 'f(){ cat < "$1"; }; f ~/.ssh/id_rsa'
    commands = guard.shell_syntax.parse(command)
    assert any(str(Path.home() / ".ssh/id_rsa") in item.redirections for item in commands)


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "f(){ trap 'echo done' EXIT; echo hi; }; f",
        't(){ printf "%s\\n" "$@" | sort; }; t b a',
        "eval 'echo hi'",
        "trap 'echo done' EXIT",
    ],
)
def test_plain_functions_traps_and_evals_still_run_unprompted(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"
