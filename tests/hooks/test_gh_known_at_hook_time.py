"""A gh call whose target and arguments the hook can fix at hook time does not ask (#253).

A repository named with -R decides the host. A fact the hook cannot fix, such as a repository the
working directory picks, or another command on the line, still asks. A glob stays a run-time word and asks (#181).
Between the hook's check and gh's run the files and variables may change (TOCTOU); #181 closes that gap.
"""

import subprocess

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project", "plain_gh_environment")


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
def test_an_unquoted_glob_in_a_read_endpoint_still_asks() -> None:
    assert decide("gh api repos/o/r/contents/f.yml?ref=0123abc -q .content") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_repository_option_does_not_skip_a_command_that_may_plant_git_on_path() -> None:
    assert decide("cp x later/git; gh pr list -R furedea/agent-config") == "ask"
