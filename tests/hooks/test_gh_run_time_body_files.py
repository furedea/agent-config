"""A body file named by set environment variables is scanned and allowed; any other run-time path asks (#181).

On a line that assigns nothing, a parameter holds the value in the hook's environment. A path the hook
cannot expand to one file, such as a lone parameter or an unset variable, still asks. Between the hook's
scan and gh's read the file may change (TOCTOU); the GitHub Gateway (#181) closes that gap.
"""

from pathlib import Path

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
    ],
)
@pytest.mark.usefixtures("logged_body_files")
def test_a_clean_existing_body_file_named_by_set_environment_variables_is_scanned_and_allowed(command: str) -> None:
    assert verdict(command)[0] == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param('gh issue edit 242 --title x --body-file "$f" >/dev/null', id="a lone variable may be any word"),
        pytest.param('gh issue comment 1 -R furedea/r -F - < "$S/body.md"', id="standard input from a run-time file"),
        pytest.param("gh issue comment 1 -R furedea/r -F $UNSET_BODY_DIR/body.md", id="a variable the hook lacks"),
        pytest.param("gh issue comment 1 -R furedea/r -F $TMPDIR/missing.md", id="a file that does not exist"),
        pytest.param(
            "gh issue comment 1 -R furedea/r -F $(echo $TMPDIR/body.md)",
            id="a path computed by a command substitution",
        ),
        pytest.param("S=/etc; gh issue comment 1 -R furedea/r -F $S/passwd", id="a variable assigned on the line"),
        pytest.param(
            "for S in /etc; do gh issue comment 1 -R furedea/r -F $S/passwd; done", id="a variable set by a loop"
        ),
    ],
)
@pytest.mark.usefixtures("logged_body_files")
def test_a_body_file_the_hook_cannot_expand_still_asks(command: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNSET_BODY_DIR", raising=False)
    assert verdict(command)[0] == "ask"


@pytest.mark.usefixtures("logged_body_files")
def test_a_body_file_holding_a_secret_is_refused_after_its_path_expands(
    logged_body_files: Path, scan_samples: dict[str, str]
) -> None:
    (logged_body_files / "body.md").write_text(next(iter(scan_samples.values())))
    assert verdict("gh issue comment 1 -R furedea/r -F $TMPDIR/body.md")[0] == "ask"


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
