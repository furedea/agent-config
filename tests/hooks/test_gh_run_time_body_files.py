"""A body file named at run time asks until the GitHub Gateway (#181); a literal body file is scanned and allowed.

The hook runs outside the sandbox with an environment that may differ from the sandboxed shell's,
so expanding a parameter there can scan another file than the one gh sends.
"""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project", "plain_gh_environment", "furedea_checkout")


def verdict(command: str) -> tuple[str, str]:
    result = guard.decide("allowed", {"tool_input": {"command": command}})
    return result.decision, result.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "gh pr create --repo furedea/agent-config --head feat/migrate-rust-style-rules --base main "
            '--title "feat(lint): migrate rust-style prose rules to checks" --body-file $TMPDIR/pr/body.md 2>&1',
            id="logged PR creation with a body file under TMPDIR",
        ),
        pytest.param(
            "gh pr edit 193 --repo furedea/agent-config --body-file $TMPDIR/pr/body.md 2>&1", id="logged PR edit"
        ),
        pytest.param("gh pr edit 188 --body-file $TMPDIR/body.md", id="logged PR edit in the working repository"),
        pytest.param(
            'gh issue create --title "test: lint test targets with clippy in CI" '
            "--body-file $S/briefs/issue_clippy.md",
            id="logged issue creation with a body file under a harness variable",
        ),
        pytest.param("gh issue comment 242 --body-file $S/plan242.md", id="logged plan comment"),
        pytest.param(
            'gh issue edit 242 --title "fix: follow-ups from #235 (Pi srt anchoring, UNC project roots)" '
            '--body-file "$f" >/dev/null',
            id="logged issue edit, with its lone body file variable quoted",
        ),
        pytest.param(
            "gh issue create --repo furedea/agent-harness --title "
            '"test: report the failing element in collapsed all() assertions" --body-file $TMPDIR/issue_all_msg.md',
            id="logged issue creation in another furedea repository",
        ),
        pytest.param(
            "gh api -X PATCH repos/furedea/skills-human-intervention/issues/comments/6845899920 "
            '-F body=@"$f.new" -q .html_url',
            id="logged comment edit from a quoted run-time file",
        ),
        pytest.param(
            "gh api -X POST repos/furedea/agent-config/issues/74/comments -F body=@$TMPDIR/plan74.md "
            "--jq '\"\\(.id) \\(.html_url)\"'",
            id="logged plan comment through the REST API",
        ),
        pytest.param('gh pr create --head topic -t x --body-file "$D/pr.md"', id="a quoted run-time body file"),
        pytest.param("gh issue comment 1 -R furedea/r -F ${S}/body.md", id="a braced parameter"),
        pytest.param('gh issue comment 1 -R furedea/r -F - < "$S/body.md"', id="standard input from a run-time file"),
    ],
)
@pytest.mark.usefixtures("logged_body_files")
def test_a_clean_existing_body_file_named_at_run_time_asks(command: str) -> None:
    decision, reason = verdict(command)
    assert decision == "ask"
    assert "named at run time" in reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr create --head topic -t x --body-file body.md", id="a relative body file"),
        pytest.param("gh issue comment 1 -R furedea/r -F notes.txt", id="a short body file option"),
        pytest.param("gh api repos/furedea/r/issues/1/comments -F body=@notes.txt", id="a REST file field"),
        pytest.param("gh issue comment 1 -R furedea/r -F - < notes.txt", id="standard input from a literal file"),
    ],
)
@pytest.mark.usefixtures("sent_files")
def test_a_clean_literal_body_file_is_scanned_and_allowed(command: str) -> None:
    assert verdict(command)[0] == "allow"
