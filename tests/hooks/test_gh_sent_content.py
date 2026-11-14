"""What a granted gh call sends to GitHub, inline, from a file, or on standard input, is scanned or asks."""

import os
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project", "plain_gh_environment")


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    ("command", "fragment"),
    [
        pytest.param(
            "gh issue comment 1 -R furedea/r -F - <<EOF\n$GH_TOKEN\nEOF", "expands", id="an unquoted heredoc body"
        ),
        pytest.param('gh issue comment 1 -R furedea/r -F - <<< "$GH_TOKEN"', "expands", id="a herestring body"),
        pytest.param("gh issue comment 1 -R furedea/r -F - 0<&3", "cannot see", id="a body from a copied descriptor"),
        pytest.param(
            "gh issue comment 1 -R furedea/r -F - 0<<EOF\n$GH_TOKEN\nEOF", "expands", id="an fd 0 unquoted heredoc"
        ),
        pytest.param("gh issue comment 1 -R furedea/r -F - <> notes.txt", "cannot see", id="a read-write redirect"),
        pytest.param("gh issue comment 1 -R furedea/r -F - < $P", "cannot see", id="an unquoted run-time file"),
        pytest.param("gh issue comment 1 -R furedea/r -F - < ~+/.env", "cannot see", id="a tilde-plus stdin file"),
        pytest.param(
            "gh pr comment 12 --body-file /dev/stdin < $P", "cannot see", id="/dev/stdin from a run-time file"
        ),
        pytest.param(
            "gh api repos/furedea/x/issues/1/comments -F body=@/dev/fd/0 <<EOF\n$GH_TOKEN\nEOF",
            "expands",
            id="/dev/fd/0 from an expanding heredoc",
        ),
        pytest.param("gh pr comment 12 -R furedea/r -F /dev/fd/3", "device", id="another descriptor file"),
        pytest.param("gh pr comment 12 -R furedea/r -F /dev/../dev/fd/3", "device", id="a descriptor file through .."),
        pytest.param("gh pr comment 12 -R furedea/r -F .", "non-regular", id="a directory"),
        pytest.param(
            "gh issue comment 1 -R furedea/r -F - < /proc/self/environ", "process", id="a process file on stdin"
        ),
        pytest.param("gh issue comment 1 -R furedea/r -F - < /dev/zero", "device", id="a device on stdin"),
        pytest.param(
            "gh issue comment 1 -R furedea/r -F - < /dev/stdin", "own standard input", id="stdin redirected from stdin"
        ),
        pytest.param(
            "gh api repos/furedea/agent-config/issues/1/comments -f body=@$GH_TOKEN",
            "parameter",
            id="a raw field value starting with @",
        ),
        pytest.param("gh pr create -R furedea/r -t x --fill", "operation table", id="a body filled from commits"),
        pytest.param('gh api -X GET search/issues --raw-field="q=$GH_TOKEN"', "endpoint", id="an attached raw field"),
        pytest.param("cat notes.txt | gh issue comment 1 -R furedea/r -F -", "pipe", id="a body from a pipe"),
        pytest.param(
            'gh issue comment 1 -R furedea/r -b "$(< .env)"', "more than print", id="a bash file substitution"
        ),
        pytest.param(
            'gh issue comment 1 -R furedea/r -b "$(cat < .env)"', "more than print", id="cat with an input file"
        ),
        pytest.param(
            'gh api -X GET search/issues --input - < "$P"', "cannot read", id="a read body from a run-time file"
        ),
        pytest.param(
            'gh issue comment 1 -R furedea/r -b "$(cat .env)"', "does more than print", id="a body read from a file"
        ),
        pytest.param(
            'gh issue comment 1 -R furedea/r -b "$(cat -- -secret)"',
            "does more than print",
            id="a body read from a dash-named file",
        ),
        pytest.param(
            'gh issue comment 1 -R furedea/r -b "$(cat)"', "does more than print", id="a body typed into cat"
        ),
        pytest.param(
            'gh pr comment 1 -R furedea/r --body-file "$(echo .env)"', "computes", id="a body file path from a command"
        ),
        pytest.param(
            'gh issue comment 1 -R furedea/r -F - < "$(echo .env)"', "computes", id="a stdin path from a command"
        ),
    ],
)
def test_input_the_guard_cannot_read_before_it_leaves_asks(command: str, fragment: str) -> None:
    verdict = guard.decide("allowed", {"tool_input": {"command": command}})
    assert verdict.decision == "ask"
    assert fragment in verdict.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "gh api graphql -f query='query($q:String!){search(query:$q){issueCount}}' -f q='TOKEN'", id="a query"
        ),
        pytest.param("gh api -X GET search/issues -f q='TOKEN'", id="a REST read"),
        pytest.param("gh issue list -R other/r --search 'TOKEN'", id="a search"),
    ],
)
def test_a_secret_in_what_a_read_sends_asks(secret_samples: dict[str, str], command: str) -> None:
    assert decide(command.replace("TOKEN", secret_samples["github_token"])) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize("sample", ["github_token", "aws_key", "rsa_header"])
def test_a_secret_in_an_inline_body_asks(secret_samples: dict[str, str], sample: str) -> None:
    command = f"gh issue comment 1 -b 'token: {secret_samples[sample]}'"
    verdict = guard.decide("allowed", {"tool_input": {"command": command}})
    assert verdict.decision == "ask"
    assert "in what this gh call sends" in verdict.reason
    assert secret_samples[sample] not in verdict.detail


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr create --head x -t y --body-file body.md", id="a body file"),
        pytest.param("gh pr create --head x -t y -F body.md", id="a short body file option"),
        pytest.param("gh api repos/furedea/r/issues/1/comments -F body=@body.md", id="a typed field file"),
        pytest.param("gh api repos/furedea/r/issues/1/comments --input body.md", id="a request body file"),
        pytest.param("gh api repos/furedea/r/issues/1/comments --input - < body.md", id="a body on standard input"),
        pytest.param("gh issue comment 1 -R furedea/r -F - < body.md", id="a body file on standard input"),
        pytest.param("gh pr comment 1 -R furedea/r -F=body.md", id="a short option with an equals sign"),
        pytest.param(
            "gh api repos/furedea/r/issues/1/comments -F=body=@body.md", id="a typed field with an equals sign"
        ),
        pytest.param("gh api graphql -f query='{ viewer { login } }' -F note=@body.md", id="a file in a read"),
        pytest.param(
            "gh api repos/furedea/r/issues/1/comments -F body=@- < ~/body.md", id="a home file on standard input"
        ),
        pytest.param("gh pr comment 12 -R furedea/r --body-file /dev/stdin < body.md", id="/dev/stdin from a file"),
    ],
)
def test_a_secret_in_a_literal_file_the_call_sends_asks(
    secret_samples: dict[str, str], command: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    for path in (Path("body.md"), tmp_path / "body.md"):
        path.write_text(f"config = {secret_samples['aws_key']}\n")
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_secret_in_a_heredoc_body_asks(secret_samples: dict[str, str]) -> None:
    command = f"gh issue comment 1 --body-file - <<'EOF'\n{secret_samples['github_token']}\nEOF"
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_body_file_without_secrets_is_allowed() -> None:
    Path("body.md").write_text("## Summary\n\nNo secrets here.\n")
    assert decide("gh pr create --head x -t y --body-file body.md") == "allow"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_fifo_the_call_sends_asks_without_being_opened() -> None:
    os.mkfifo("body.fifo")
    assert decide("gh pr comment 1 -R furedea/r --body-file body.fifo") == "ask"
    assert decide("gh pr comment 1 -R furedea/r -F - < body.fifo") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_run_time_path_the_environment_expands_is_scanned(
    secret_samples: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BODY_DIR", str(tmp_path))
    (tmp_path / "body.md").write_text(f"config = {secret_samples['aws_key']}\n")
    assert decide('gh pr comment 1 -R furedea/r --body-file "$BODY_DIR/body.md"') == "ask"
    assert decide('gh api repos/furedea/r/issues/1/comments -F body=@"$BODY_DIR/body.md"') == "ask"
    (tmp_path / "clean.md").write_text("No secrets.\n")
    assert decide('gh pr comment 1 -R furedea/r --body-file "$BODY_DIR/clean.md"') == "allow"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_run_time_path_expanding_to_a_device_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVICE_DIR", "/dev")
    assert decide('gh pr comment 1 -R furedea/r --body-file "$DEVICE_DIR/null"') == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_an_unset_parameter_expands_to_nothing_before_the_scan(secret_samples: dict[str, str]) -> None:
    Path(".env.md").write_text(f"config = {secret_samples['aws_key']}\n")
    assert decide('gh issue comment 1 -R furedea/r -F "${UNSET_PREFIX}.env.md"') == "ask"
    assert decide('gh issue comment 1 -R furedea/r -F "$UNSET_PREFIX$PWD/.env.md"') == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_file_larger_than_the_scan_reads_asks() -> None:
    Path("big.md").write_text("x" * 100001)
    assert decide("gh issue comment 1 -R furedea/r -F big.md") == "ask"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize("path", ['"$BODY_DIR:h/body.md"', '"$BODY_DIR"/../body.md\\x', '~"$BODY_DIR"/body.md'])
def test_a_run_time_path_the_shell_may_expand_differently_stays_unscanned(
    secret_samples: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setenv("BODY_DIR", str(tmp_path))
    (tmp_path / "body.md").write_text(f"config = {secret_samples['aws_key']}\n")
    # Scanning the file the guard would wrongly expand to would ask; left unscanned, a trusted write passes.
    assert decide(f"gh pr comment 1 -R furedea/r --body-file {path}") == "allow"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_quoted_tilde_names_a_directory_called_tilde(
    secret_samples: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (home / "body.md").write_text("No secrets.\n")
    Path("~").mkdir()
    Path("~/body.md").write_text(f"config = {secret_samples['aws_key']}\n")
    assert decide("gh issue comment 1 -R furedea/r -F '~/body.md'") == "ask"
    assert decide("gh issue comment 1 -R furedea/r -F '~nosuchuser0123/x'") == "allow"
