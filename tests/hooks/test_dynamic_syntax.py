"""Shell functions, loops, and substitutions run unprompted unless a program with external effect hides in them."""

from pathlib import Path

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
        'f() { alias x="$1"; }; f "gh pr merge 1"',
    ],
)
def test_text_that_the_shell_runs_as_code_asks_when_computed(kind: str, command: str) -> None:
    verdict = decide(kind, command)
    assert verdict.decision == "ask"
    assert "review" in verdict.reason


@pytest.mark.parametrize(
    "command",
    ["trap 'gh pr merge 1' EXIT", "trap '-x; gh pr merge 1' EXIT", "builtin eval 'gh pr merge 1'"],
)
def test_a_literal_trap_or_eval_script_is_judged_as_a_script(command: str) -> None:
    assert decide("allowed", command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    ["trap 'echo \"$tmp\" >&2' EXIT", "trap - EXIT", "trap -p", "trap INT", "alias", "alias ll"],
)
def test_traps_of_sandbox_local_commands_and_alias_lookups_run_unprompted(kind: str, command: str) -> None:
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
        "builtin eval 'git commit --no-verify -m x'",
    ],
)
def test_denials_see_every_command_in_a_function_body_or_trap_or_beside_a_computed_call(command: str) -> None:
    assert decide("forbidden", command).decision == "deny"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "alias g=gh\ng pr merge 1",
        "alias c='git commit'\nc --no-verify -m x",
        "alias ll='ls -l'",
        'alias x="$X"',
        "alias -g G='| sh'",
    ],
)
def test_an_alias_definition_asks_because_its_value_joins_whatever_follows_its_name(kind: str, command: str) -> None:
    verdict = decide(kind, command)
    assert verdict.decision == "ask"
    assert "review" in verdict.reason


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_function_reading_a_relative_script_asks_since_it_may_run_after_a_cd(
    kind: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "nested").mkdir()
    (isolated_project / "nested/script.sh").write_text("git commit --no-verify -m x\n")
    verdict = decide(kind, "f(){ sh < script.sh; }; cd nested; f")
    assert verdict.decision == "ask"


def test_a_function_reading_an_absolute_script_is_judged_by_its_text(isolated_project: Path) -> None:
    script = isolated_project / "script.sh"
    script.write_text("git commit --no-verify -m x\n")
    assert decide("forbidden", f"f(){{ sh < {script}; }}; cd /; f").decision == "deny"


@pytest.mark.parametrize(
    "template",
    [
        "trap 'sh < script.sh' EXIT; cd nested",
        "for d in a b; do sh < script.sh; cd nested; done",
        "while true; do sh < script.sh; cd nested; done",
        "for ((i = 0; i < 2; i++)); do sh < script.sh; cd nested; done",
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_relative_script_read_by_a_trap_or_a_repeated_loop_body_asks(
    kind: str, template: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "nested").mkdir()
    (isolated_project / "nested/script.sh").write_text("git commit --no-verify -m x\n")
    assert decide(kind, template).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "alias -- -g=gh",
        "aliases[g]=gh\ng pr merge 1",
        "typeset aliases[g]=gh",
        "galiases[G]='| sh'",
        "functions[f]='gh pr merge 1'\nf",
        "dis_functions[f]=x",
    ],
)
def test_defining_an_alias_or_function_through_any_spelling_asks(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_relative_script_read_once_outside_any_body_is_still_judged_by_its_text(
    kind: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    assert decide(kind, "sh < script.sh; for d in a b; do echo $d; done").decision == "allow"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "f(){ sh; }; f <<'EOF'\ngit commit --no-verify -m x\nEOF",
        "f(){ bash; }; echo 'gh pr merge 1' | f",
        "f(){ sh; }; f < script.sh",
        "f(){ bash -s x; }; f",
    ],
)
def test_a_shell_in_a_function_body_reading_the_callers_input_asks(
    kind: str, command: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("git commit --no-verify -m x\n")
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "f(){ echo 'echo hi' | sh; }; f",
        "f(){ sh <<'EOF'\necho hi\nEOF\n}; f",
    ],
)
def test_a_shell_in_a_function_body_with_its_own_literal_input_is_judged_by_it(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        ": ${aliases[g]::=gh}",
        ": ${BASH_ALIASES[g]:=gh}",
        "BASH_ALIASES[g]=gh",
        "BASH_CMDS[gh]=./evil",
        "commands[gh]=./evil",
        "set -A aliases g gh",
        "printf -v 'BASH_ALIASES[g]' gh",
        "read -A functions",
        "hash -p ./evil gh",
        "hash gh=./evil",
    ],
)
def test_replacing_what_a_command_name_runs_asks(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command", ["hash", "hash -r", "hash gh", "mkdir functions", "git commit -q -m 'add functions'"]
)
def test_hash_lookups_and_the_words_alone_run_unprompted(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "template",
    [
        "for d in a b; do cd nested; done; sh < script.sh",
        "f(){ cd nested; }; f; f; sh < script.sh",
        "trap 'cd nested' DEBUG; sh < script.sh",
        "eval 'cd nested'; sh < script.sh",
    ],
)
def test_a_relative_script_read_after_a_repeated_or_hidden_cd_asks(
    kind: str, template: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "nested/nested").mkdir(parents=True)
    (isolated_project / "nested/script.sh").write_text("echo safe\n")
    (isolated_project / "nested/nested/script.sh").write_text("git commit --no-verify -m x\n")
    assert decide(kind, template).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "trap '-x; git commit --no-verify -m x' EXIT",
        'f(){ find . "$@"; }; f -delete',
        'f(){ find . -"$1"; }; f delete',
        "f(){ find . $*; }; f -delete",
        'f(){ find . "${1}"; }; f -delete',
        "f(){ find . \"$@\"; }; eval 'f -delete'",
        "f(){ find . \"$@\"; }; trap 'f -delete' EXIT",
        'f(){ find . "$@"; }; g(){ f -delete; }; g',
        'f(){ shift; find . "$1"; }; f x -delete',
        "f(){ find . \"$1\"; }; f '-delete'",
    ],
)
def test_denials_see_a_function_body_with_the_arguments_of_each_call(command: str) -> None:
    assert decide("forbidden", command).decision == "deny"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "printf -vBASH_ALIASES[g] gh",
        "print -valiases[g] gh",
        "hash -rp ./evil gh",
        "declare -n x=BASH_ALIASES; x[g]=gh",
        "x='BASH_ALIASES[g]'; printf -v \"$x\" gh",
        'printf -v "$NAME" gh',
    ],
)
def test_dash_led_trap_actions_inherited_input_and_indirect_parameter_writes_ask(
    kind: str, command: str, isolated_project: Path
) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "evil.sh").write_text("git commit --no-verify -m x\n")
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize("command", ["trap -p EXIT", "trap -l", "trap -- 'echo hi' EXIT", "hash -r"])
def test_trap_and_hash_inspection_forms_run_unprompted(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "allow"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_shell_in_a_function_body_trusts_no_input_from_outside_the_body(kind: str, isolated_project: Path) -> None:
    (isolated_project / "script.sh").write_text("echo safe\n")
    (isolated_project / "evil.sh").write_text("git commit --no-verify -m x\n")
    command = f"{{ f(){{ sh; }}; }} < {isolated_project / 'script.sh'}; f < {isolated_project / 'evil.sh'}"
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        'f(){ find . "$@"; }; f -delete; f(){ :; }',
        "f(){ find . \"$@\"; }; 'f' -delete",
        "f(){ id=$1; find . $id; }; f -delete",
        "f(){ find . $1; }; f 'x -delete'",
        'f(){ id=$1; find . $id; }; f "x -delete"',
        'f(){ local id="$1"; find . "$id"; }; f -delete',
    ],
)
def test_denials_follow_redefined_quoted_and_copied_function_arguments(command: str) -> None:
    assert decide("forbidden", command).decision == "deny"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        'f(){ find . "${1/x/-delete}"; }; f xx',
        'f(){ id=$1; find . "${id/x/-delete}"; }; f xx',
        'f(){ find . "${@:1}"; }; f -delete',
        'f(){ x="-$1"; find . "$x"; }; f delete',
        "f(){ for a; do find . $a; done; }; f -delete",
        'f(){ set -- -delete; find . "$1"; }; f',
        'f(){ getopts d: o; find . -"$OPTARG"; }; f -d elete',
        "f(){ find . $argv; }; f -delete",
        'printf -v"$x" gh',
        'read -r "$name"',
    ],
)
def test_function_arguments_or_parameter_names_the_respelling_cannot_follow_ask(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "f(){ find . $1; }; f '-delet?'",
        "f(){ find . $1; }; f '-del[e]te'",
        "IFS=x; f(){ find . $1; }; f 'ax-delete'",
        "f(){ local IFS=x; find . $1; }; f 'ax-delete'",
    ],
)
def test_an_unquoted_argument_whose_globbing_or_splitting_the_respelling_cannot_follow_asks(
    kind: str, command: str
) -> None:
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
@pytest.mark.parametrize(
    "command",
    [
        "printf -v IFS x; f(){ find . $1; }; f 'ax-delete'",
        "read -r IFS <<< x; f(){ find . $1; }; f 'ax-delete'",
        "declare -n r=IFS; r=x; f(){ find . $1; }; f 'ax-delete'",
        "printf -v I''FS x; f(){ find . $1; }; f 'ax-delete'",
        "declare 'I''FS=x'; f(){ find . $1; }; f 'ax-delete'",
        'y=I; declare -n r="${y}FS"; r=x; f(){ find . $1; }; f ax-delete',
    ],
)
def test_any_spelling_that_names_ifs_beside_a_function_asks(kind: str, command: str) -> None:
    assert decide(kind, command).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        'f(){ builtin shift; find . "$1"; }; f x -delete',
        'f(){ command shift; find . "$1"; }; f x -delete',
        "eval -- 'git commit --no-verify -m x'",
        'f(){ find . "$1"; }; f -delete',
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
