"""A write without a named repository acts on the one gh picks for the working directory, judged the same way."""

import subprocess
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project", "plain_gh_environment")


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


def add_remote(name: str, url: str) -> None:
    subprocess.run(["git", "remote", "add", name, url], check=True, capture_output=True)


@pytest.mark.parametrize(
    ("remotes", "expected"),
    [
        pytest.param({"origin": "git@github.com:furedea/agent-config.git"}, "allow", id="a trusted SSH origin"),
        pytest.param({"origin": "https://github.com/other/agent-config"}, "ask", id="another owner's origin"),
        pytest.param(
            {"origin": "https://github.com/furedea/fork", "upstream": "https://github.com/other/project"},
            "ask",
            id="an upstream remote gh may pick",
        ),
        pytest.param({"origin": "https://gitlab.com/furedea/agent-config"}, "ask", id="no GitHub remote"),
        pytest.param(
            {"origin": "https://github.com/furedea/x", "upstream": "http://github.com/other/r"},
            "ask",
            id="a remote URL the guard cannot read",
        ),
        pytest.param({}, "ask", id="no remote"),
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_write_to_the_working_repository_follows_every_github_remote(remotes: dict[str, str], expected: str) -> None:
    subprocess.run(["git", "init", "--quiet"], check=True)
    for name, url in remotes.items():
        add_remote(name, url)
    assert decide("gh issue comment 1 -b ok") == expected


@pytest.mark.parametrize(("resolved", "expected"), [("other/project", "ask"), ("furedea/agent-config", "allow")])
def test_a_default_repository_set_by_gh_names_the_working_repository(
    furedea_checkout: Path, resolved: str, expected: str
) -> None:
    subprocess.run(["git", "config", "remote.origin.gh-resolved", resolved], check=True, cwd=furedea_checkout)
    assert decide("gh issue comment 1 -b ok") == expected


@pytest.mark.usefixtures("furedea_checkout")
def test_gh_repo_in_the_hook_environment_names_the_working_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_REPO", "other/r")
    assert decide("gh issue comment 1 -b ok") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_another_gh_host_in_the_hook_environment_makes_every_call_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_HOST", "ghe.example")
    assert decide("gh issue comment 1 -R furedea/agent-config -b ok") == "ask"
    assert decide("gh pr view 1") == "ask"


@pytest.mark.parametrize(
    ("origin", "expected"),
    [("https://github.com/other/r", "ask"), ("https://github.com/furedea/agent-config", "allow")],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_related_issue_does_not_stand_in_for_the_working_repository(origin: str, expected: str) -> None:
    subprocess.run(["git", "init", "--quiet"], check=True)
    add_remote("origin", origin)
    assert decide("gh issue edit 1 --parent https://github.com/furedea/x/issues/2") == expected


@pytest.mark.parametrize(
    ("origin", "expected"),
    [("https://github.com/other/r", "ask"), ("https://github.com/furedea/agent-config", "allow")],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_branch_repository_does_not_stand_in_for_the_issue_repository(origin: str, expected: str) -> None:
    subprocess.run(["git", "init", "--quiet"], check=True)
    add_remote("origin", origin)
    assert decide("gh issue develop 5 --branch-repo furedea/agent-config") == expected
