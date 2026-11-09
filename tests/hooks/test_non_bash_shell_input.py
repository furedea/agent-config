"""A shell the guard cannot parse is never trusted with a script, however the script reaches it (#87)."""

from pathlib import Path

import pytest

from tests.runtime import load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

DELETE = "gh repo delete x --yes"
MERGE = "gh pr merge 76 --merge"


def verdict(kind: str, command: str) -> str:
    return guard.decide(kind, {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"nu --commands '{DELETE}'", id="nu --commands"),
        pytest.param(f"pwsh -Command '{DELETE}'", id="pwsh -Command"),
        pytest.param(f"pwsh -c '{DELETE}'", id="pwsh -c"),
        pytest.param(f"powershell -NoProfile -Command {DELETE}", id="powershell unquoted words"),
        pytest.param(f"fish -c '{DELETE}'", id="fish -c"),
        pytest.param(f"echo '{DELETE}' | fish", id="fish reading a pipe"),
        pytest.param(f"echo '{DELETE}' | pwsh", id="pwsh reading a pipe"),
        pytest.param(f"fish <<EOF\n{DELETE}\nEOF", id="fish heredoc"),
        pytest.param(f"nu <<< '{DELETE}'", id="nu here-string"),
        pytest.param(f"nohup pwsh -Command '{DELETE}'", id="behind a wrapper"),
        pytest.param(f"echo '{DELETE}' | ysh", id="a shell known only by its name, on a pipe"),
        pytest.param(f"lolsh <<EOF\n{DELETE}\nEOF", id="a shell known only by its name, heredoc"),
        pytest.param(f"ysh <<< '{DELETE}'", id="a shell known only by its name, here-string"),
        pytest.param(f"nu -e '{DELETE}'", id="nu -e is --execute, not an encoded script"),
        pytest.param(f"fish --init-command='{DELETE}'", id="fish --init-command attached"),
        pytest.param(f"fish --init-command '{DELETE}'", id="fish --init-command separate"),
        pytest.param(f"fish -C '{DELETE}'", id="fish -C"),
        pytest.param(f"echo '{DELETE}' | pwsh -Command -", id="pwsh -Command - reads the pipe"),
        pytest.param(f"pwsh-preview /Command '{DELETE}'", id="pwsh-preview /Command"),
        pytest.param(f"pwsh-preview7 --c '{DELETE}'", id="versioned pwsh-preview --c"),
        pytest.param(f"echo '{DELETE}' | fish -C 'echo init'", id="an init command beside a script on the pipe"),
        pytest.param(f"FISH -c '{DELETE}'", id="upper case name"),
        pytest.param(f"PWSH /Command '{DELETE}'", id="upper case PowerShell name"),
        pytest.param(f"BASH -c '{DELETE}'", id="upper case bash name"),
        pytest.param(f"pwsh --c '{DELETE}'", id="pwsh --c"),
        pytest.param(f"pwsh --command '{DELETE}'", id="pwsh --command"),
        pytest.param(f"pwsh /c '{DELETE}'", id="pwsh /c"),
        pytest.param(f"powershell /Command '{DELETE}'", id="powershell /Command"),
    ],
)
def test_a_visible_script_that_matches_a_deny_rule_is_denied(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"pwsh -Command '{MERGE}'", id="pwsh -Command"),
        pytest.param(f"pwsh -command '{MERGE}'", id="pwsh -command lower case"),
        pytest.param(f"pwsh -COMMAND '{MERGE}'", id="pwsh -COMMAND upper case"),
        pytest.param(f"echo '{MERGE}' | fish", id="fish reading a pipe"),
        pytest.param(f"fish <<EOF\n{MERGE}\nEOF", id="fish heredoc"),
        pytest.param(f"nu --commands '{MERGE}'", id="nu --commands"),
    ],
)
def test_a_visible_script_that_matches_an_ask_prefix_asks(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("pwsh -e SQBHAGUAbABsAG8A", id="pwsh -e"),
        pytest.param("pwsh -ec SQBHAGUAbABsAG8A", id="pwsh -ec"),
        pytest.param("pwsh -EncodedCommand SQBHAGUAbABsAG8A", id="pwsh -EncodedCommand"),
        pytest.param("pwsh --encodedcommand SQBHAGUAbABsAG8A", id="pwsh --encodedcommand"),
        pytest.param("pwsh --ec SQBHAGUAbABsAG8A", id="pwsh --ec"),
        pytest.param("pwsh /e SQBHAGUAbABsAG8A", id="pwsh /e"),
        pytest.param("powershell -enc SQBHAGUAbABsAG8A", id="powershell -enc"),
        pytest.param("nu --execute 'ls'", id="nu --execute"),
        pytest.param("pwsh -Command 'Get-ChildItem'", id="a harmless script"),
        pytest.param('pwsh -Command "$CMD"', id="a computed script"),
        pytest.param("echo 'ls' | fish", id="a harmless script on a pipe"),
        pytest.param("cat script.fish | fish", id="a script of unknown text on a pipe"),
        pytest.param("fish <<EOF\nls\nEOF", id="a harmless heredoc"),
        pytest.param("fish <<EOF\n$CMD\nEOF", id="a computed heredoc"),
        pytest.param("fish < script.fish", id="a script file"),
        pytest.param("echo 'ls' | ysh", id="a shell known only by its name, harmless script"),
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_script_the_guard_cannot_judge_asks(kind: str, command: str) -> None:
    assert verdict(kind, command) == "ask"


@pytest.mark.parametrize("shell", ["fish", "nu", "nushell", "pwsh", "powershell", "pwsh-preview", "ysh", "xonsh"])
@pytest.mark.parametrize(
    "arguments",
    [
        "",
        "--version",
        "--help",
        "script.txt",
        "-NoProfile",
        "\N{EN DASH}Command 'ls'",
        "\N{EM DASH}e SQBHAGUA",
        "--c 'ls'",
        "/c 'ls'",
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_known_foreign_shell_asks_however_it_is_invoked(kind: str, shell: str, arguments: str) -> None:
    assert verdict(kind, f"{shell} {arguments}".strip()) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "/opt/bin/fish --version",
        "nohup fish",
        "env A=1 pwsh",
        "fish3 --version",
        "PWSH -c 'ls'",
        "Fish --version",
        "/usr/local/bin/NU script.nu",
    ],
)
def test_a_known_foreign_shell_asks_by_path_wrapper_version_and_letter_case(command: str) -> None:
    assert verdict("allowed", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"pwsh -Command '-not $false; {DELETE}'", id="-Command"),
        pytest.param(f"pwsh -c '-not $false; {DELETE}'", id="-c"),
        pytest.param(f"pwsh -com '-not $false; {DELETE}'", id="abbreviated -com"),
        pytest.param(f"pwsh --command '-not $false; {DELETE}'", id="--command"),
        pytest.param(f"pwsh /c '-not $false; {DELETE}'", id="/c"),
        pytest.param(f"pwsh -NonInteractive -Command '-not $false; {DELETE}'", id="after an option holding c"),
        pytest.param(f"pwsh -Command -not true\\; {DELETE}", id="unquoted words"),
    ],
)
def test_powershell_code_starting_with_a_dash_is_still_read_for_deny_rules(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"pwsh -CommandWithArgs '-not $false; {DELETE}' arg1", id="-CommandWithArgs"),
        pytest.param(f"pwsh -cwa '-not $false; {DELETE}' arg1", id="-cwa"),
        pytest.param(f"pwsh --commandwithargs '-not $false; {DELETE}'", id="--commandwithargs"),
    ],
)
def test_powershell_command_with_args_keeps_its_first_word_as_code(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


def test_powershell_command_with_args_hands_the_rest_to_the_code_as_arguments() -> None:
    assert verdict("forbidden", f"pwsh -cwa 'Write-Output' '{DELETE}'") == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "pwsh -Command '-not $false'",
        "pwsh -NonInteractive -Command 'Get-ChildItem'",
        "pwsh -NonInteractive 'Get-ChildItem'",
        "pwsh -ExecutionPolicy Bypass -Command 'Get-ChildItem'",
        "pwsh -Command -not",
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_powershell_code_starting_with_a_dash_still_asks(kind: str, command: str) -> None:
    assert verdict(kind, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("fish script.fish", id="a script file"),
        pytest.param("fish -C 'echo init' script.fish", id="after -C with a value"),
        pytest.param("fish --init-command='echo init' script.fish", id="after an attached --init-command"),
        pytest.param("fish --init-command 'echo init' script.fish", id="after a separate --init-command"),
        pytest.param("fish -N -C 'echo init' script.fish", id="after a flag and a valued option"),
        pytest.param("fish -d 3 script.fish", id="after -d with a value"),
        pytest.param("fish --init-com 'echo init' script.fish", id="after an abbreviated --init-command"),
        pytest.param("fish --profile-s out.txt script.fish", id="after an abbreviated --profile-startup"),
        pytest.param("fish --deb 3 script.fish", id="after an abbreviated --debug"),
        pytest.param("fish --debug 3 script.fish", id="after --debug with a value"),
        pytest.param("fish script.fish arg", id="followed by a positional argument"),
        pytest.param("fish -- script.fish", id="after the end of options"),
        pytest.param("/opt/bin/fish script.fish", id="by path"),
        pytest.param("fish -i -n script.fish", id="interactive cancels -n"),
        pytest.param("fish -in script.fish", id="interactive and -n in one bundle"),
        pytest.param("fish --interactive --no-execute script.fish", id="long interactive cancels --no-execute"),
        pytest.param("fish --no-execute -i script.fish", id="interactive after --no-execute"),
    ],
)
def test_a_fish_script_file_that_matches_a_deny_rule_is_denied(isolated_project: Path, command: str) -> None:
    (isolated_project / "script.fish").write_text(f"{DELETE}\n")
    assert verdict("forbidden", command) == "deny"


def test_a_fish_script_file_is_read_in_the_directory_it_runs_in(isolated_project: Path) -> None:
    (isolated_project / "sub").mkdir()
    (isolated_project / "sub" / "script.fish").write_text(f"{DELETE}\n")
    assert verdict("forbidden", "cd sub && fish script.fish") == "deny"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("fish script.fish", id="a harmless file"),
        pytest.param("fish missing.fish", id="a file that does not exist"),
        pytest.param("fish -C 'echo init' script.fish", id="a harmless file after -C"),
        pytest.param('fish "$SCRIPT"', id="a computed file name"),
        pytest.param("fish -c 'echo hi' script.fish", id="a -c script before the file"),
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_fish_script_file_the_guard_cannot_judge_asks(isolated_project: Path, kind: str, command: str) -> None:
    (isolated_project / "script.fish").write_text("echo hi\n")
    assert verdict(kind, command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"fish script.fish; {DELETE}", id="a denied command after the fish call"),
        pytest.param(f"{DELETE}; fish script.fish", id="a denied command before the fish call"),
        pytest.param(f"fish -C 'echo init' script.fish && {DELETE}", id="after -C"),
    ],
)
@pytest.mark.parametrize(
    "text",
    [
        pytest.param("if true\n    echo hi\nend\n", id="if and end"),
        pytest.param("set -l x (date)\n", id="a command substitution in fish syntax"),
    ],
)
def test_a_fish_script_file_in_fish_syntax_does_not_hide_a_denied_sibling(
    isolated_project: Path, command: str, text: str
) -> None:
    (isolated_project / "script.fish").write_text(text)
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("fish -n script.fish", id="-n"),
        pytest.param("fish --no-execute script.fish", id="--no-execute"),
        pytest.param("fish --no-exec script.fish", id="abbreviated --no-exec"),
        pytest.param("fish -Nn script.fish", id="-n in a bundle"),
        pytest.param("fish -n -C 'echo init' script.fish", id="-n before a valued option"),
        pytest.param("fish --version script.fish", id="--version prints and exits"),
        pytest.param("fish -v script.fish", id="-v prints and exits"),
        pytest.param("fish --help script.fish", id="--help prints and exits"),
        pytest.param("fish -h script.fish", id="-h prints and exits"),
        pytest.param("fish --print-debug-categories script.fish", id="--print-debug-categories prints and exits"),
    ],
)
@pytest.mark.parametrize("kind", ["allowed", "forbidden"])
def test_a_fish_syntax_check_only_asks_and_never_denies_the_file(
    isolated_project: Path, kind: str, command: str
) -> None:
    (isolated_project / "script.fish").write_text(f"{DELETE}\n")
    assert verdict(kind, command) == "ask"


def test_a_fish_script_file_in_fish_syntax_asks(isolated_project: Path) -> None:
    (isolated_project / "script.fish").write_text(f"if true\n    {DELETE}\nend\n")
    assert verdict("forbidden", "fish script.fish") == "ask"


def test_a_fish_script_file_matching_an_ask_prefix_asks(isolated_project: Path) -> None:
    (isolated_project / "script.fish").write_text(f"{MERGE}\n")
    assert verdict("allowed", "fish script.fish") == "ask"


def test_a_fish_positional_argument_is_not_read_as_the_script() -> None:
    command = f"fish -c 'printf \"%s\\n\" $argv;' '{DELETE}'"
    assert verdict("forbidden", command) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "./run.sh -c conf",
        "ssh host ls",
        "lolsh --help",
        "lolsh script.txt",
        "echo fish",
        "man fish",
        "echo hi | cat",
        "echo hi | grep h",
    ],
)
def test_names_and_arguments_that_are_no_foreign_shell_keep_their_verdict(command: str) -> None:
    assert verdict("allowed", command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("git commit --no-verif -m x", id="git commit --no-verif"),
        pytest.param("git commit --no-veri -m x", id="git commit --no-veri"),
        pytest.param("git commit -m x --no-veri", id="git commit trailing --no-veri"),
        pytest.param("python3 -W ignore -m pip install x", id="python -W with a value"),
        pytest.param("python3 -X dev -m pip install x", id="python -X with a value"),
        pytest.param("python3 -IW ignore -m pip install x", id="python bundled -W with a value"),
        pytest.param("python3 -W ignore -X dev -m ensurepip", id="python two valued options"),
        pytest.param("python3 -Wignore -m pip install x", id="python -W attached"),
        pytest.param("python3 --check-hash-based-pycs never -m pip install x", id="python long valued option"),
        pytest.param("python3 -Wignore::DeprecationWarning -m pip install x", id="python -W attached with colons"),
        pytest.param("python3 -Xutf8=0 -m pip install x", id="python -X attached with equals"),
        pytest.param("python3 -IXutf8=0 -m ensurepip", id="python bundled -X attached with equals"),
    ],
)
def test_abbreviated_and_valued_options_do_not_hide_a_denied_form(command: str) -> None:
    assert verdict("forbidden", command) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "git commit --no-edit -m x",
        "git commit --no-verbose -m x",
        "git commit --no-status -m x",
        "python3 -W ignore -m pytest",
        "python3 -X dev script.py",
        "python3 -W ignore script.py pip",
    ],
)
def test_the_wider_option_patterns_keep_ordinary_forms_allowed(command: str) -> None:
    assert verdict("forbidden", command) == "allow"
