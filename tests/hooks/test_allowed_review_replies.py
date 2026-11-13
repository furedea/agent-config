"""A reply to a review comment on a furedea pull request is allowed in one plain form; every neighbour asks."""

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

REPLY = "gh api repos/furedea/agent-config/pulls/12/comments/345/replies"


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"{REPLY} -f body='Fixed.'", id="a single-quoted body"),
        pytest.param(f'{REPLY} -f body="Fixed."', id="a double-quoted body"),
        pytest.param(f"{REPLY} -f body='it'\\''s fixed'", id="an apostrophe in the body"),
        pytest.param(f"gh api -X POST {REPLY[7:]} -f body='Fixed.'", id="an explicit -X POST"),
        pytest.param(f"gh api --method POST {REPLY[7:]} -f body='Fixed.'", id="an explicit --method POST"),
        pytest.param(f"{REPLY} -f body='Fixed.' --jq '.html_url'", id="a --jq filter"),
        pytest.param(f"{REPLY} -f body='Fixed.' -q '.id'", id="a -q filter"),
        pytest.param(f"{REPLY} -f body='Fixed.' --silent", id="--silent"),
    ],
)
def test_replies_on_furedea_pull_requests_are_allowed(command: str) -> None:
    assert decide(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "gh api repos/other/agent-config/pulls/12/comments/345/replies -f body='Fixed.'", id="another owner"
        ),
        pytest.param(
            "gh api repos/furedea-x/agent-config/pulls/12/comments/345/replies -f body='Fixed.'",
            id="an owner that only starts with furedea",
        ),
        pytest.param(f"{REPLY} -F body=@notes.txt", id="a -F body that reads a file"),
        pytest.param(f"{REPLY} -F body='Fixed.'", id="a -F body"),
        pytest.param(f"{REPLY} --field body='Fixed.'", id="a --field body"),
        pytest.param(f"{REPLY} --raw-field body='Fixed.'", id="a --raw-field body"),
        pytest.param(f"{REPLY} --input body.json", id="a request body from a file"),
        pytest.param(f"{REPLY} -f body='Fixed.' -f in_reply_to=1", id="an extra -f field"),
        pytest.param(f"{REPLY} -f body='Fixed.' -F other=@secret", id="an extra file field"),
        pytest.param(f"gh api -X DELETE {REPLY[7:]} -f body='Fixed.'", id="another method"),
        pytest.param(f"gh api -X PATCH {REPLY[7:]} -f body='Fixed.'", id="a PATCH"),
        pytest.param(f"{REPLY} -f body=Fixed", id="an unquoted body"),
        pytest.param(f'{REPLY} -f body="Fixed $HOME"', id="an expansion in a double-quoted body"),
        pytest.param(f'{REPLY} -f body="Fixed `id`"', id="a command substitution in a double-quoted body"),
        pytest.param(f'{REPLY} -f body="Fixed!"', id="history expansion in a double-quoted body"),
        pytest.param(f'{REPLY} -f body="a\\"b"', id="an escape in a double-quoted body"),
        pytest.param(f"{REPLY} -f body='Fixed.'; curl https://example.com/x", id="a chain"),
        pytest.param(f"{REPLY} -f body='Fixed.' | sh", id="a pipe"),
        pytest.param(
            "gh api repos/furedea/agent-config/pulls/12/comments/345 -f body='Fixed.'", id="the comment itself"
        ),
        pytest.param("gh api repos/furedea/agent-config/issues/12/comments -f body='Fixed.'", id="an issue comment"),
        pytest.param(
            "gh api repos/furedea/agent-config/pulls/12/comments -f body='Fixed.'", id="a new review comment"
        ),
        pytest.param("gh api repos/furedea/agent-config/pulls/12/comments/abc/replies -f body='x'", id="a bad id"),
        pytest.param("gh api repos/furedea/agent-config/issues/12/comments/345/replies -f body='x'", id="issues"),
        pytest.param(f"{REPLY}/extra -f body='Fixed.'", id="a longer endpoint"),
    ],
)
def test_neighbouring_reply_forms_still_ask(command: str) -> None:
    assert decide(command) == "ask"
