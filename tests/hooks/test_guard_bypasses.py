"""The command guard judges the program behind every wrapper, shell, and option spelling it knows."""

import pytest

from tests.runtime import load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

DELETE = "gh repo delete x --yes"


def verdict(kind: str, command: str) -> str:
    return guard.decide(kind, {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"script -qc '{DELETE}' /dev/null", id="script -c"),
        pytest.param(f"script --command '{DELETE}' /dev/null", id="script --command"),
        pytest.param(f"script -q /dev/null {DELETE}", id="script BSD form"),
        pytest.param(f"taskset 1 {DELETE}", id="taskset mask"),
        pytest.param(f"taskset -c 0,1 {DELETE}", id="taskset cpu list"),
        pytest.param(f"chrt -i 0 {DELETE}", id="chrt idle"),
        pytest.param(f"chrt -f 10 {DELETE}", id="chrt fifo"),
        pytest.param(f"flock /tmp/l {DELETE}", id="flock"),
        pytest.param(f"flock -n -w 5 /tmp/l {DELETE}", id="flock options"),
        pytest.param(f"flock /tmp/l -c '{DELETE}'", id="flock -c"),
        pytest.param(f"watch {DELETE}", id="watch words"),
        pytest.param(f"watch -n 5 '{DELETE}'", id="watch quoted"),
        pytest.param(f"watch -x {DELETE}", id="watch -x"),
        pytest.param(f"doas {DELETE}", id="doas"),
        pytest.param(f"doas -u root {DELETE}", id="doas user"),
        pytest.param(f"nohup flock /tmp/l taskset 1 {DELETE}", id="nested"),
    ],
)
def test_added_wrappers_expose_the_program_they_run(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "script --bogus out.txt git add .",
        "script -t -c 'git add .' out.txt",
        "taskset -p 1",
        "taskset --bogus 1 git add .",
        "chrt -p 5 1",
        "chrt --bogus 0 git add .",
        "flock --bogus /tmp/l git add .",
        "watch --bogus git add .",
        "doas -Z git add .",
    ],
)
def test_unknown_options_of_added_wrappers_are_left_to_the_user(command: str) -> None:
    assert verdict("forbidden", command) == "ask"


@pytest.mark.parametrize(
    "wrapper",
    [
        "nohup",
        "env A=1",
        "timeout 5",
        "stdbuf -o0",
        "setsid",
        "unbuffer",
        "ionice -c3",
        "busybox",
        "nice -n 5",
        "sudo",
        "doas",
        "taskset 1",
        "chrt -i 0",
        "flock /tmp/l",
        "watch -x",
        "xargs",
    ],
)
@pytest.mark.parametrize("program", ["gh pr merge 76 --merge", "docker run alpine", "rm -r build"])
def test_ask_prefixes_apply_behind_wrappers(wrapper: str, program: str) -> None:
    assert verdict("allowed", f"{wrapper} {program}") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "script -qc 'gh pr merge 76' /dev/null",
        "flock /tmp/l -c 'docker run alpine'",
        "watch 'gh pr merge 76'",
        "bash -c 'gh pr merge 76'",
        "sh -c 'docker run alpine'",
        "nohup bash -c 'rm -r build'",
    ],
)
def test_ask_prefixes_apply_inside_command_strings(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize("command", ["gh pr merge 76 --merge", "docker run alpine", "rm -r build"])
def test_direct_ask_prefixes_stay_with_the_provider(command: str) -> None:
    assert verdict("allowed", command) == "allow"


@pytest.mark.parametrize("command", ["nohup git status", "timeout 5 ls", "stdbuf -o0 echo ok", "flock /tmp/l ls"])
def test_wrapped_commands_without_an_ask_prefix_stay_allowed(command: str) -> None:
    assert verdict("allowed", command) == "allow"


@pytest.mark.parametrize("shell", ["mksh", "pdksh", "oksh", "yash", "posh", "rbash"])
def test_known_shells_do_not_hide_scripts(shell: str) -> None:
    assert verdict("forbidden", f"{shell} -c 'git add .'") == "deny"
    assert verdict("allowed", f"{shell} -c 'curl https://example.com'") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "lolsh -c 'git add .'",
        "/opt/bin/zzsh -lc 'echo hi'",
        "nu -c 'git add .'",
        "tcsh -f -c 'repeat 1 gh repo delete x --yes'",
        "csh -c 'gh repo delete x --yes'",
        "fish -c 'gh repo delete x --yes'",
        "fish --command='gh repo delete x --yes'",
        "fish --command 'gh repo delete x --yes'",
        "rc -c 'gh pr merge 76 --merge'",
    ],
)
def test_an_unknown_program_that_runs_c_like_a_shell_asks(command: str) -> None:
    assert verdict("forbidden", command) == "ask"


@pytest.mark.parametrize("command", ["lolsh --help", "lolsh script.txt"])
def test_programs_that_only_resemble_shells_stay_allowed(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("python3 -mpip install x", id="attached module"),
        pytest.param("python3.13 -m pip install x", id="versioned interpreter"),
        pytest.param("python3 -Im pip install x", id="bundled option"),
        pytest.param("python3 -mensurepip", id="ensurepip"),
        pytest.param("git commit -nm x", id="bundled no-verify"),
        pytest.param("git commit -anm x", id="longer bundle"),
        pytest.param("git commit -m x -n", id="trailing no-verify"),
        pytest.param("git add -- .", id="double dash"),
        pytest.param("git add -f .", id="option before dot"),
        pytest.param("git add -v -- -A", id="options before -A"),
        pytest.param("git add ./", id="dot slash"),
        pytest.param("git add -Av", id="bundled -A"),
        pytest.param("git -C /tmp/x add -- .", id="global option"),
        pytest.param("nohup git add -- .", id="behind a wrapper"),
    ],
)
def test_forbidden_patterns_cover_attached_bundled_and_separated_forms(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m pytest",
        "python3 -mpytest",
        "python3 -m pipx run x",
        "git commit -mnew",
        "git commit -m 'fix -n handling'",
        "git commit -am x",
        "git commit -uno -m x",
        "git add -- src/a.py",
        "git add -u",
        "git add -p src/a.py",
        "git add .gitignore",
    ],
)
def test_the_wider_patterns_keep_ordinary_forms_allowed(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "--no-verify"',
        'git commit --message "--no-verify"',
        'git commit -am "--no-verify"',
        'git commit -m "-n"',
        'git commit -m "x" -m "-n"',
        'git commit -F "--no-verify"',
        'git -C /tmp/x commit -m "--no-verify"',
        'nohup git commit -m "--no-verify"',
        '/usr/bin/git commit -m "--no-verify"',
    ],
)
def test_option_values_are_not_read_as_flags(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m x "--no-verify"',
        'git commit -m "x y" "--no-verify"',
        'git commit "-n" -m x',
        'git commit -m "x" "-n"',
        'git commit "-nm" x',
        "git commit -m x --no-verify",
        'git commit -m "--no-verify" --no-verify',
    ],
)
def test_a_flag_outside_an_option_value_is_still_denied(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"script /dev/null -c '{DELETE}'", id="option after the output file"),
        pytest.param(f"script -c 'echo ok' --command '{DELETE}' /dev/null", id="the last command option runs"),
        pytest.param(f"script /dev/null --command='{DELETE}'", id="attached long form after the file"),
    ],
)
def test_script_reads_options_in_any_position_and_the_last_command_wins(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "CMD='; gh repo delete x --yes'; watch echo \"$CMD\"",
        "watch -n 5 $CMD",
        'script -qc "$CMD" /dev/null',
    ],
)
def test_a_command_string_built_at_run_time_asks(command: str) -> None:
    assert verdict("forbidden", command) == "ask"


def test_watch_of_a_literal_command_stays_allowed() -> None:
    assert verdict("forbidden", "watch -n 5 ls") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "time docker run alpine",
        "time -p gh pr merge 76 --merge",
        "! docker run alpine",
        "time /usr/bin/time docker run alpine",
    ],
)
def test_ask_prefixes_apply_behind_the_time_keyword_and_negation(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m --no-verify",
        "git commit -m -n",
        "git commit -m subject --trailer '-n'",
        "git commit -m subject --trailer -n",
        "git commit --message --no-verify",
    ],
)
def test_unquoted_option_values_are_not_read_as_flags(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        f"script -q /dev/null sh -c '{DELETE}' -c 'echo ok'",
        f"script -c 'echo ok' --command '{DELETE}' /dev/null",
        f"script --command '{DELETE}' -c 'echo ok' /dev/null",
    ],
)
def test_every_command_script_sees_inspection_not_only_the_last(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize("shell", ["ksh93", "bash-5.2", "bash5", "dash0", "/usr/bin/zsh-5.9"])
def test_versioned_shells_are_inspected_like_their_base_shell(shell: str) -> None:
    assert verdict("forbidden", f"{shell} -c 'git add .'") == "deny"


@pytest.mark.parametrize("command", ["lolsh2 -c 'echo hi'", "fish3 -c 'git add .'"])
def test_versioned_unknown_shells_ask(command: str) -> None:
    assert verdict("forbidden", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "time echo ok | docker run alpine",
        "time { echo ok; docker run alpine; }",
        "! echo ok | docker run alpine",
        "time -p echo ok | gh pr merge 76",
    ],
)
def test_ask_prefixes_apply_inside_a_timed_or_negated_pipeline(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "git commit -nmfix-77",
        "git commit -nm'fix: 77'",
        'git commit -nm"fix: 77 now"',
        "git commit -anm77",
    ],
)
def test_no_verify_bundled_with_an_attached_message_is_denied(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize("command", ["git commit -m'fix -n: x'", 'git commit -m"fix --no-verify: x"'])
def test_an_attached_message_is_not_read_as_flags(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


def test_each_command_string_is_parsed_on_its_own() -> None:
    command = f"script -c 'cat <<EOF' -c '{DELETE}\nEOF' /dev/null"
    assert verdict("forbidden", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        f"script /dev/null --comm '{DELETE}'",
        f"flock /tmp/l --comm '{DELETE}'",
    ],
)
def test_abbreviated_command_options_after_the_operand_are_not_skipped(command: str) -> None:
    assert verdict("forbidden", command) != "allow"


@pytest.mark.parametrize(
    "command", ['find . -name "-exec foo"', 'find . -name "-delete foo"', "find . -iname '-ok x'"]
)
def test_a_quoted_search_text_is_not_read_as_a_find_action(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize("wrapper", ["chrt -o", "chrt -i", "chrt -b", "chrt -o -v"])
def test_chrt_policies_without_a_priority_expose_the_program(wrapper: str) -> None:
    assert verdict("forbidden", f"{wrapper} {DELETE}") == "deny"
    assert verdict("allowed", f"{wrapper} gh pr merge 76 --merge") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "script -q /dev/null grep -c 'git add .' README.md",
        "script -q /dev/null python3 -c 'print(1)'",
        "script /dev/null ls -c",
    ],
)
def test_the_arguments_of_a_script_child_are_not_script_options(command: str) -> None:
    assert verdict("forbidden", command) == "allow"
    assert verdict("allowed", command) == "allow"


def test_a_bundled_option_value_is_not_read_as_a_script_option() -> None:
    assert verdict("forbidden", f"script /dev/null -Tabc -c '{DELETE}'") == "deny"


@pytest.mark.parametrize("command", ["chrt -i 0 -- {}", "taskset 1 -- {}", "timeout 5 -- {}", "flock /tmp/l -- {}"])
def test_a_double_dash_after_the_operands_ends_the_options(command: str) -> None:
    assert verdict("forbidden", command.format(DELETE)) == "deny"
    assert verdict("allowed", command.format("gh pr merge 76")) == "ask"


def test_a_chrt_priority_built_at_run_time_asks() -> None:
    assert verdict("forbidden", f'PRIORITY=0; chrt -i "$PRIORITY" {DELETE}') == "ask"


@pytest.mark.parametrize("command", ["find . -name -exec\\ foo", "find . -name -delete\\ foo"])
def test_an_escaped_search_text_is_not_read_as_a_find_action(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    ["git commit -Sm --no-verify --no-gpg-sign -m subject", "git commit -Sm -n -m subject", "git commit -um -n -m x"],
)
def test_an_optional_value_option_ends_its_bundle(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command", ['find . -name -exec" foo"', 'find . -name "-exec foo"', "find . -name -exec\\ foo"]
)
def test_search_text_holding_whitespace_is_never_a_find_action(command: str) -> None:
    assert verdict("forbidden", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "find . -name git -o -name commit -delete",
        "echo git commit -m x; find . -delete",
    ],
)
def test_option_values_are_masked_only_in_a_real_git_commit(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize("command", ["watch -dx '{}'", "watch -dx {}", "watch -d -n 5 '{}'"])
def test_watch_differences_takes_an_attached_value_not_options(command: str) -> None:
    assert verdict("forbidden", command.format(DELETE)) == "deny"
