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
        "f(){ X=$1 sh -c 'find . \"$X\"'; }; f -delete",
        "true(){ find . \"$1\"; }; eval 't\\rue -delete'",
        'g(){ find . "$1"; }; eval \'"g" -delete\'',
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
        'noglob(){ find . "$1"; }; noglob -delete',
        'f(){ x=$1; }; f -delete; find . "$x"',
        "f(){ x=$1; }; f -delete; eval 'find . \"$x\"'",
        "setopt auto_cd; for d in a b; do nested; sh < script.sh; done",
        "for d in a b; do chdir nested; sh < script.sh; done",
        "for d in a b; do c\\\nd nested; sh < script.sh; done",
        "setopt a_u_t_o_cd; for d in a b; do nested; sh < script.sh; done",
        "set -J; for d in a b; do nested; sh < script.sh; done",
        "c=cd; for d in a b; do $c nested; sh < script.sh; done",
        'f(){ x=$1; }; f -delete; n=x; find . "${!n}"',
        "f(){ export x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        "set -a; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        'f(){ find . "$2"; }; mapfile -t -C f -c 1 <<< -delete',
        'f(){ find . "$2"; }; readarray -C "f" -c 1 <<< -delete',
        'f(){ find . "$1"; }; PROMPT_COMMAND=f',
        "set -e -a; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        "setopt ALL_EXPORT; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        "set -o all_export; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        "set -e -J; for d in a b; do nested; sh < script.sh; done",
        "builtin set -J; for d in a b; do nested; sh < script.sh; done",
        "command set -a; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        "nocorrect set -a; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        'f(){ find . "$2"; }; c=$(printf f); mapfile -t -C "$c" -c 1 <<< -delete',
        'f(){ find . "$1"; }; precmd_functions+=("$(printf f)")',
        'f(){ find . "$1"; }; c=$(printf mapfile); $c -C "$(printf f)" -c 1 <<< -delete',
        'f(){ find . "$1"; }; set -A precmd_functions "$(printf f)"',
        'f(){ find . "$2"; }; zargs -- "$(printf x)" -- f',
        "c=$(printf set); $c -a; f(){ x=$1; sh -c 'find . \"$x\"'; }; f -delete",
        'f(){ find . "${x:-$1}"; }; f -delete',
        'f(){ find . "${x/y/$1}"; }; f -delete',
        'f(){ x=-delete1; find . "${x%$#}"; }; f a',
        'f(){ find . "$2"; }; mapfile -t -Cf -c1 <<< -delete',
        'f(){ find . "$1"; }; c=$(printf f); "$c" -delete',
        "c=cd; for d in a b; do builtin $c nested; sh < script.sh; done",
        "c=cd; for d in a b; do command -p $c nested; sh < script.sh; done",
        'f(){ printf %s "$1" | { read -r id; find . "$id"; }; }; f -delete',
        'f(){ read -r id <<EOF\n$1\nEOF\nfind . "$id"; }; f -delete',
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


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        'git commit --allow-empty -m "close the aliases[...] hole"',
        "jq '.commands[0]' package.json",
        "grep -rn BASH_FUNC_ .",
    ],
)
def test_text_that_only_mentions_code_parameters_runs_unprompted(
    kind: str, command: str, isolated_project: Path
) -> None:
    (isolated_project / "package.json").write_text("{}\n")
    assert decide(kind, command).decision != "ask"
