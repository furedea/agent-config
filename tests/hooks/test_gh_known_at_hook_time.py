"""A gh call whose target and arguments the hook can fix at hook time does not ask (#253).

A repository named with -R decides the host, a glob that matches no file is the word as written, and a
set environment variable expands to its value. A fact the hook cannot fix, such as a repository the
working directory picks, a glob with a match, an assigned variable, or a substitution, still asks.
Between the hook's check and gh's run the files and variables may change (TOCTOU); #181 closes that gap.
"""

import subprocess
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project", "plain_gh_environment")
TREE = "gh api repos/furedea/reusable-workflows/contents/.github/workflows/adr-lint.yml?ref=0123abc -q .content"


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


def checkout_with_remote(url: str) -> None:
    subprocess.run(["git", "init", "--quiet"], check=True)
    subprocess.run(["git", "remote", "add", "origin", url], check=True, capture_output=True)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr checks 251 -R furedea/agent-config", id="a check read"),
        pytest.param("gh pr view 251 -R furedea/agent-config --json body", id="a view with a field list"),
        pytest.param("gh pr view 251 --repo furedea/agent-config", id="the long option"),
        pytest.param("gh pr view 251 --repo=furedea/agent-config", id="the long option with an equals sign"),
        pytest.param("gh pr view 251 -Rfuredea/agent-config", id="the short option joined to its value"),
        pytest.param("gh pr view 251 -R github.com/furedea/agent-config", id="an explicit github.com host"),
        pytest.param("gh pr view 251 -R other/repo", id="another owner, which a read may name"),
    ],
)
@pytest.mark.parametrize("origin", ["https://evil.example/o/r", "https://github.com/furedea/agent-config"])
def test_a_read_naming_its_repository_ignores_the_working_directory_remote(command: str, origin: str) -> None:
    checkout_with_remote(origin)
    assert decide(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr view 251", id="no repository option"),
        pytest.param("gh pr view 251 -R evil.example/o/r", id="another host in the option"),
        pytest.param("gh pr view 251 -R https://evil.example/o/r", id="another host as a URL"),
        pytest.param("gh pr view 251 -R $REPO", id="a repository known only at run time"),
        pytest.param("gh pr view 251 -q -R furedea/agent-config", id="an option that may take the -R as its value"),
        pytest.param("gh pr view 251 -R", id="an option without a value"),
        pytest.param(
            "gh pr view 251 -R furedea/agent-config -R evil.example/o/r", id="a later option on another host"
        ),
    ],
)
def test_a_read_not_naming_a_github_repository_follows_the_working_directory_remote(command: str) -> None:
    checkout_with_remote("https://evil.example/o/r")
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_repository_option_does_not_override_a_host_set_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_HOST", "evil.example")
    assert decide("gh pr view 251 -R furedea/agent-config") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_glob_matching_no_file_is_the_argument_as_written() -> None:
    assert decide(TREE) == "allow"
    assert decide("gh api repos/furedea/agent-config/git/trees/HEAD?recursive=1 --jq '.tree[].path'") == "allow"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"mkdir -p x && {TREE}", id="another command on the line"),
        pytest.param(f"touch a; {TREE}", id="a command before"),
        pytest.param(f"{TREE} | head", id="a pipeline"),
    ],
)
def test_a_glob_on_a_line_with_other_commands_still_asks(command: str) -> None:
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_glob_matching_a_file_still_asks() -> None:
    Path("repos").mkdir()
    Path("repos/furedea").mkdir()
    (Path("repos/furedea") / "x").write_text("")
    assert decide("gh api repos/furedea/?  -q .id") == "ask"
    assert decide("gh api repos/furedea/* -q .id") == "ask"
    # a glob this narrow matches in the working directory too
    (Path("repos/furedea") / "agent-config.git").write_text("")
    assert decide("gh api repos/furedea/agent-config?git -q .id") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh api repos/o/r/contents/~/x?y -q .id", id="a tilde"),
        pytest.param("gh api repos/o/r/contents/{a,b}?x -q .id", id="a brace"),
        pytest.param("gh api repos/o/r/contents/$X?y -q .id", id="a parameter"),
        pytest.param("gh api repos/o/r/contents/*(.)?y -q .id", id="a zsh qualifier"),
        pytest.param("gh api repos/o/r/contents/$(echo x)?y -q .id", id="a command substitution"),
        pytest.param("gh api -X POST repos/o/r/issues/1/comments?x -f body=y", id="a write to another owner"),
    ],
)
def test_a_glob_with_another_expansion_still_asks(command: str) -> None:
    assert decide(command) == "ask"
