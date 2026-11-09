"""A shell the guard cannot parse is never trusted with a script, however the script reaches it (#87)."""

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


@pytest.mark.parametrize("command", ["/opt/bin/fish --version", "nohup fish", "env A=1 pwsh", "fish3 --version"])
def test_a_known_foreign_shell_asks_by_path_wrapper_and_version(command: str) -> None:
    assert verdict("allowed", command) == "ask"


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
        pytest.param(f"git commit --no-ver -m x", id="git commit --no-ver"),
        pytest.param(f"git commit -m x --no-v", id="git commit --no-v"),
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
        "git commit --no-status -m x",
        "python3 -W ignore -m pytest",
        "python3 -X dev script.py",
        "python3 -W ignore script.py pip",
    ],
)
def test_the_wider_option_patterns_keep_ordinary_forms_allowed(command: str) -> None:
    assert verdict("forbidden", command) == "allow"
