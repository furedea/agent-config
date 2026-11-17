"""Forms a gh call could use to slip past the guard: clone settings and destinations, split words, devices."""

import subprocess
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("furedea_checkout", "plain_gh_environment")


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "key", ["http.proxy", "http.https://github.com/.proxy", "http.sslVerify", "http.sslCAInfo", "http.curloptResolve"]
)
def test_a_clone_under_a_proxy_or_tls_setting_asks(key: str) -> None:
    assert decide("gh repo clone furedea/agent-config") == "allow"
    subprocess.run(["git", "config", key, "x"], check=True)
    assert decide("gh repo clone furedea/agent-config") == "ask"


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ("fresh", "allow"),
        ("/tmp/x/config", "ask"),
        ("~/.config/git", "ask"),
        ("../elsewhere", "ask"),
        (".git/sub", "ask"),
        ("existing", "ask"),
    ],
)
def test_a_clone_destination_must_be_a_new_plain_subdirectory(destination: str, expected: str) -> None:
    Path("existing").mkdir()
    assert decide(f"gh repo clone furedea/agent-config {destination}") == expected


def test_an_expanded_body_path_into_proc_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("D", "/proc/self")
    assert decide('gh issue comment 1 -R furedea/agent-config -F "$D/environ"') == "ask"
    assert decide('gh issue comment 1 -R furedea/agent-config -F "$PWD/../../../../../../dev/stdin"') == "ask"


def test_an_unquoted_parameter_beside_text_splits_on_its_value(monkeypatch: pytest.MonkeyPatch) -> None:
    Path("secret.md").write_text("x\n")
    Path("secret.md 1").write_text("x\n")
    monkeypatch.setenv("X", "secret.md ")
    assert decide("gh issue comment -R furedea/agent-config -F ${X}1") == "ask"
    monkeypatch.setenv("R", "agent-config")
    assert decide("gh pr list --repo furedea/$R") == "allow"
    monkeypatch.setenv("R", "x --web")
    assert decide("gh pr list --repo furedea/$R") == "ask"


def test_a_clone_destination_beside_another_command_asks() -> None:
    assert decide("true; gh repo clone furedea/agent-config fresh") == "ask"
    assert decide("true; gh repo clone furedea/agent-config") == "allow"
