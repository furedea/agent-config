"""Git options and settings that skip repository hooks are denied; option values that only spell them are not."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_git.py", "guard_git")
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
        ("git", "commit", "-m", "--", "--no-verify"),
        ("git", "commit", "--message", "--", "-n"),
        ("git", "am", "-S", "--no-verify", "p.patch"),
        ("git", "am", "-S", "-n", "p.patch"),
        ("git", "commit", "--no-verify", "--verify", "-m", "x"),
        ("git", "commit", "--no-verify", "--pathspec-from-file", "--verify"),
        ("git", "commit", "--no-post-rewrite", "--post-rewrite", "-m", "x"),
        ("git", "commit", "--no-verify", "--verify", "--no-post-rewrite"),
        ("git", "-c", "alias.ci=commit -n", "ci"),
        ("git", "-c", "Include.path=/x", "commit"),
        ("git", "-c", "includeIf.gitdir:/.path=/x", "commit"),
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
        ("git", "commit", "-uno", "-m", "x"),
        ("git", "commit", "-um", "-m", "x"),
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


@pytest.mark.parametrize(
    "command",
    [
        "git commit $FLAGS",
        'git commit "$FLAG" -m x',
        "git rebase $F main",
        "git merge $BRANCH",
        "git push origin topic $F",
        "git -c $C commit -m x",
        'git -c "$C" push origin topic',
        'git -c "$C" status',
        "git --config-env=$C commit -m x",
        "git commit -m $MESSAGE",
        "git merge -m $A $B",
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_run_time_words_where_a_hook_skipping_option_could_be_are_left_to_the_user(command: str) -> None:
    assert guard.decide({"tool_input": {"command": command}}).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "$MESSAGE"',
        'git commit -m "$(cat msg.txt)" --allow-empty',
        'git commit -F "$FILE"',
        'git commit -m x -- "$FILE"',
        'git rebase -x "$CMD" main',
        "git -C $W commit -m x",
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_run_time_option_values_and_paths_do_not_need_review(command: str) -> None:
    assert guard.decide({"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
        'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="core.hooksPath" GIT_CONFIG_VALUE_0=/dev/null git commit -m x',
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hookspath GIT_CONFIG_VALUE_0=/x git push origin b",
        "GIT_CONFIG_KEY_3=alias.ci git ci",
        "GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/x'\" git commit -m x",
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_environment_settings_that_move_the_hooks_are_denied(command: str) -> None:
    verdict = guard.decide({"tool_input": {"command": command}})
    assert verdict.decision == "deny"
    assert REASON in verdict.reason


@pytest.mark.parametrize(
    "command",
    [
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=a git commit -m x",
        "GIT_AUTHOR_NAME=a git commit -m x",
        "env GIT_AUTHOR_NAME=a git status",
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_other_environment_settings_pass(command: str) -> None:
    assert guard.decide({"tool_input": {"command": command}}).decision == "allow"


@pytest.mark.parametrize(
    "command",
    [
        'git commit --no-verify "$FILE"',
        'git merge --no-verify "$BRANCH"',
        "git commit -n -m $MESSAGE",
        'git -c core.hooksPath=/x commit -m "$MESSAGE"',
        'GIT_CONFIG_KEY_0=core.hooksPath git commit "$FILE"',
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_settled_hook_skip_is_denied_even_beside_a_run_time_word(command: str) -> None:
    verdict = guard.decide({"tool_input": {"command": command}})
    assert verdict.decision == "deny"
    assert REASON in verdict.reason


@pytest.mark.usefixtures("isolated_project")
def test_a_run_time_operand_without_a_forbidden_option_is_still_reviewed() -> None:
    assert guard.decide({"tool_input": {"command": 'git merge "$BRANCH"'}}).decision == "ask"


@pytest.mark.parametrize(
    "command",
    [
        'git merge "$BRANCH"; git commit -n -m x',
        'git push origin "$B" && git commit --no-verify -m x',
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_hook_skip_in_a_later_segment_is_denied_before_an_earlier_review(command: str) -> None:
    assert guard.decide({"tool_input": {"command": command}}).decision == "deny"
