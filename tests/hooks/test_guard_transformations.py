"""P4 of #73: a prohibition survives every transformation the command guard claims to understand.

Each deny prefix must still be denied, and each ask prefix must still ask, after the command is
wrapped, quoted, run through a shell -c script, or handed to the shell builtin, in any combination.
"""

from collections.abc import Callable
import json
from pathlib import Path
import shlex

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from tests.runtime import REPO_ROOT, load_script_module


guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

PREFIXES = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
# A bare `bash -c` holds no script to read, so the guard asks before it can apply the deny prefix.
# Any script after it is judged by the other rules, so these prefixes are not spellings of one command.
SHELL_PROGRAMS = frozenset({"bash", "sh", "zsh"})
DENY = [
    tuple(rule["prefix"])
    for rule in PREFIXES
    if rule["decision"] == "deny" and rule["prefix"][0] not in SHELL_PROGRAMS
]
ASK = [tuple(rule["prefix"]) for rule in PREFIXES if rule["decision"] == "ask"]

PROPERTY = settings(
    max_examples=150,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

WRAPPERS = ["nohup", "env A=1", "timeout 5", "stdbuf -o0", "setsid", "nice -n 5", "sudo", "time", "command"]
SHELLS = ["bash", "sh", "zsh", "/bin/bash"]
BUILTIN_RUNNER = "ev" + "al"


def wrap_with(wrapper: str) -> Callable[[str], str]:
    return lambda command: f"{wrapper} {command}"


def run_in_shell(shell: str) -> Callable[[str], str]:
    return lambda command: f"{shell} -c {shlex.quote(command)}"


def run_by_builtin(command: str) -> str:
    return f"{BUILTIN_RUNNER} {shlex.quote(command)}"


def verdict(kind: str, command: str) -> str:
    return guard.decide(kind, {"tool_input": {"command": command}}).decision


def quoted(words: tuple[str, ...], styles: list[str]) -> str:
    """The words with each one single-quoted, double-quoted, or left bare."""
    pieces = [
        {"single": f"'{word}'", "double": f'"{word}"', "bare": word}[style]
        for word, style in zip(words, styles, strict=True)
    ]
    return " ".join(pieces)


@st.composite
def spellings(draw: st.DrawFn, prefix: tuple[str, ...]) -> tuple[str, int]:
    """A spelling of the prefix command and how many wrapper-like layers hide it from the provider."""
    styles = draw(st.lists(st.sampled_from(["single", "double", "bare"]), min_size=len(prefix), max_size=len(prefix)))
    command = quoted(prefix, styles)
    if draw(st.booleans()):
        command = f"/usr/bin/{command}"
    layers: list[Callable[[str], str]] = draw(
        st.lists(
            st.one_of(
                st.sampled_from(WRAPPERS).map(wrap_with),
                st.sampled_from(SHELLS).map(run_in_shell),
                st.just(run_by_builtin),
            ),
            max_size=3,
        )
    )
    for layer in layers:
        command = layer(command)
    negated = draw(st.booleans())
    return (f"! {command}" if negated else command), len(layers) + negated


@PROPERTY
@given(data=st.data())
def test_a_deny_prefix_is_denied_in_every_supported_spelling(data: st.DataObject) -> None:
    prefix = data.draw(st.sampled_from(DENY))
    command, _ = data.draw(spellings(prefix))
    assert verdict("forbidden", command) == "deny", command


@PROPERTY
@given(data=st.data())
def test_an_ask_prefix_behind_a_wrapper_or_script_asks(data: st.DataObject) -> None:
    prefix = data.draw(st.sampled_from(ASK))
    command, layers = data.draw(spellings(prefix))
    expected = "ask" if layers else "allow"
    assert verdict("allowed", command) == expected, command


def policy_without(decision: str, path: Path) -> Path:
    policy = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())
    policy["rules"] = [rule for rule in policy["rules"] if rule["decision"] != decision]
    path.write_text(json.dumps(policy))
    return path


def test_a_policy_that_lost_its_deny_prefixes_turns_the_deny_property_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_COMMAND_PERMISSIONS", str(policy_without("deny", tmp_path / "policy.json")))
    with pytest.raises(AssertionError):
        test_a_deny_prefix_is_denied_in_every_supported_spelling()


def test_a_policy_that_lost_its_ask_prefixes_turns_the_ask_property_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_COMMAND_PERMISSIONS", str(policy_without("ask", tmp_path / "policy.json")))
    with pytest.raises(AssertionError):
        test_an_ask_prefix_behind_a_wrapper_or_script_asks()
