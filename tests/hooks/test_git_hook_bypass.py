"""Git options and settings that skip repository hooks are denied; option values that only spell them are not."""

import pytest
from tests.runtime import load_script_module

git = load_script_module("agents/hooks/lib/git_safety.py", "git_safety")

REASON = "skips repository hooks; let the hooks run"


@pytest.mark.parametrize(
    "arguments",
    [
        ("git", "commit", "--no-verify", "-m", "x"),
        ("git", "commit", "-n", "-m", "x"),
        ("git", "commit", "-nm", "x"),
        ("git", "commit", "-anm", "x"),
        ("git", "commit", "-m", "x", "--no-ver"),
        ("git", "commit", "--amend", "--no-post-rewrite"),
        ("git", "push", "--no-verify", "origin", "b"),
        ("git", "push", "origin", "b", "--no-verify"),
        ("git", "push", "--no-ver", "origin", "b"),
        ("git", "merge", "--no-verify", "topic"),
        ("git", "pull", "--no-verify"),
        ("git", "am", "--no-verify", "p.patch"),
        ("git", "am", "-n", "p.patch"),
        ("git", "rebase", "--no-verify", "main"),
        ("git", "-C", "..", "commit", "--no-verify"),
        ("/usr/bin/git", "commit", "-n"),
        ("git", "-c", "core.hooksPath=/dev/null", "commit", "-m", "x"),
        ("git", "-c", "core.hooksPath=/dev/null", "status"),
        ("git", "-c", "CORE.HOOKSPATH=/x", "push", "origin", "b"),
        ("git", "-c", "user.name=a", "-c", "core.hookspath=/x", "commit"),
        ("git", "--config-env=core.hooksPath=HOOKS", "commit"),
    ],
)
def test_options_that_skip_hooks_are_denied(arguments: tuple[str, ...]) -> None:
    assert REASON in git.reason(arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        ("git", "commit", "-m", "--no-verify"),
        ("git", "commit", "-m", "-n"),
        ("git", "commit", "-m--no-verify"),
        ("git", "commit", "-mn", "--allow-empty"),
        ("git", "commit", "--message=--no-verify"),
        ("git", "commit", "--message", "--no-verify"),
        ("git", "commit", "-F", "-n"),
        ("git", "commit", "-m", "x", "--", "-n"),
        ("git", "commit", "--verify", "-m", "x"),
        ("git", "push", "--verify", "origin", "b"),
        ("git", "push", "-o", "--no-verify", "origin", "b"),
        ("git", "push", "-n", "origin", "b"),
        ("git", "push", "--dry-run", "origin", "b"),
        ("git", "rebase", "-n", "main"),
        ("git", "rebase", "-x", "--no-verify", "main"),
        ("git", "rebase", "--exec=--no-verify", "main"),
        ("git", "cherry-pick", "-n", "abc"),
        ("git", "revert", "-n", "abc"),
        ("git", "merge", "--no-ff", "topic"),
        ("git", "merge", "--no-verify-signatures", "topic"),
        ("git", "pull", "--verify-signatures"),
        ("git", "-c", "user.name=core.hooksPath", "commit", "-m", "x"),
        ("git", "-c", "core.hooksPathX=/x", "status"),
        ("git", "log", "--no-verify"),
    ],
)
def test_values_and_unrelated_forms_that_only_spell_the_option_are_allowed(arguments: tuple[str, ...]) -> None:
    assert git.reason(arguments) == ""
