"""gh calls are judged by effect: reads and reversible writes to a trusted owner's repository pass, the rest asks.

Commands marked "logged" are the gh prompts recorded on 2026-11-14; a logged command that the log cut
short is completed with the closing text its form needs.
"""

import json
import subprocess
from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")

REPLIES = "repos/furedea/agent-config/pulls/193/comments"
RESOLVE = 'resolveReviewThread(input:{threadId:"PRRT_kwDOVVcfb863Y9LM"}){thread{isResolved}}'


def decide(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).decision


def reason(command: str) -> str:
    return guard.decide("allowed", {"tool_input": {"command": command}}).reason


def add_remote(name: str, url: str) -> None:
    subprocess.run(["git", "remote", "add", name, url], check=True, capture_output=True)


@pytest.fixture(autouse=True)
def plain_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GH_REPO", "GH_HOST"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def furedea_checkout(isolated_project: Path) -> Path:
    subprocess.run(["git", "init", "--quiet"], check=True)
    add_remote("origin", "https://github.com/furedea/agent-config.git")
    return isolated_project


@pytest.fixture
def secret_samples() -> dict[str, str]:
    return json.loads(Path(__file__).with_name("secret_content_samples.json").read_text())


@pytest.mark.usefixtures("furedea_checkout")
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
            "--body-file $f >/dev/null",
            id="logged issue edit",
        ),
        pytest.param(
            "gh issue create --repo furedea/agent-harness --title "
            '"test: report the failing element in collapsed all() assertions" --body-file $TMPDIR/issue_all_msg.md',
            id="logged issue creation in another furedea repository",
        ),
        pytest.param(
            f'gh api {REPLIES}/4571531779/replies -f body="Fixed in bf5c61f: the rule now skips \\`get_mut\\`, '
            '\\`get_unchecked\\` and \\`get_unchecked_mut\\`, and functions inside a trait." --jq .html_url',
            id="logged reply with escaped backticks",
        ),
        pytest.param(
            f'gh api {REPLIES}/4571555450/replies -f body="Fixed in 47d4fa7: the pattern is now '
            '\\`Path::new(&(\\$A + \\$B))\\`, with an invalid test case." --jq .html_url',
            id="logged reply with escaped dollars",
        ),
        pytest.param(
            "gh api -X POST repos/furedea/agent-harness/pulls/245/comments/4559753097/replies "
            '-f body="Fixed in b475352: only git\'s terminating newline is removed from the toplevel."',
            id="logged reply with an explicit POST",
        ),
        pytest.param(
            "gh api repos/furedea/agent-harness/pulls/247/comments/4560088038/replies "
            '-f body="修正した: common dir の末尾が空白になるよう '
            "\\`git init --separate-git-dir 'spaced gitdir '\\` を使った\"",
            id="logged reply in Japanese with an option inside the body",
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
        pytest.param(
            f"gh api graphql -f query='mutation{{a:{RESOLVE} b:{RESOLVE.replace('Y9LM', 'Y9Ma')}}}'"
            " --jq '.data|length'",
            id="logged batch of thread resolutions",
        ),
        pytest.param(
            "gh api graphql -f query='mutation { a: " + RESOLVE + " b: unresolveReviewThread(input:{threadId:"
            '"PRRT_x"}) { thread { isResolved } } }\'',
            id="logged spaced resolution beside an unresolution",
        ),
        pytest.param(
            "gh api graphql -f query='mutation($t:ID!,$b:String!){addPullRequestReviewThreadReply("
            "input:{pullRequestReviewThreadId:$t,body:$b}){comment{id}}}' -f t=PRRT_x -f b='Fixed.'",
            id="a thread reply through GraphQL",
        ),
        pytest.param("gh api repos/furedea/agent-config/issues/2/sub_issues -F sub_issue_id=9", id="a sub-issue link"),
        pytest.param('gh pr create --head topic --body-file "$D/pr.md"', id="a quoted run-time body file"),
        pytest.param(
            "gh pr create --head topic --title 'fix: x' "
            "--body \"$(cat <<'EOF'\nUse `git add -A` never.\n$HOME stays.\nEOF\n)\"",
            id="a PR body inline through a quoted heredoc",
        ),
        pytest.param(
            "gh pr edit 242 --body \"$(printf '%s' 'pass ${a[@]} or \"$@\" or $1 through')\"",
            id="expansion text inside a substituted body",
        ),
        pytest.param("gh pr review 42 --comment -b 'Looks good'", id="a review comment"),
        pytest.param("gh pr review 42 -cb 'Looks good'", id="a bundled review comment"),
        pytest.param("gh pr close 42", id="a PR close"),
        pytest.param("gh pr ready 42 --undo", id="a draft toggle"),
        pytest.param("gh run rerun 123 --failed", id="a run rerun"),
        pytest.param("gh run cancel 123", id="a run cancel"),
        pytest.param("gh label create bug --color FF0000 -d 'Something broke'", id="a label"),
        pytest.param("gh stack submit --auto", id="a non-interactive stack submit"),
        pytest.param("gh pr comment https://github.com/furedea/agent-config/pull/1 -b ok", id="a URL target"),
        pytest.param("gh issue comment 1 -R FUREDEA/agent-config -b ok", id="an owner in another case"),
        pytest.param("gh issue comment 1 --repo=github.com/furedea/agent-config -b ok", id="a host-qualified repo"),
        pytest.param("gh issue comment 1 -b ok | head -1", id="a write piped through a filter"),
        pytest.param("gh issue comment 1 -b ok && gh pr list", id="a write in an && list"),
    ],
)
def test_reversible_writes_to_a_trusted_owner_are_allowed(command: str) -> None:
    assert decide(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh run list --commit $(git rev-parse HEAD) --json databaseId,name,status", id="logged run list"),
        pytest.param("gh run watch $R --repo furedea/agent-config --exit-status 2>&1", id="logged run watch"),
        pytest.param("gh pr view $n --json number,state --jq '\"\\(.number) \\(.state)\"'", id="logged PR view"),
        pytest.param(
            "gh pr view $n --repo furedea/agent-config --json body --jq .body > $TMPDIR/pr$n.md",
            id="logged PR body saved to a file",
        ),
        pytest.param(
            'gh pr list --repo furedea/$r --state merged --search "74 in:body" --limit 30 --json number,title '
            "--jq '.[]|\"#\\(.number) \\(.title)\"' 2>/dev/null",
            id="logged PR search",
        ),
        pytest.param(
            "gh api repos/furedea/$r/commits/main --jq '\"'$r' main \\(.sha[0:7]) "
            '\\(.commit.message|split("\\n")[0])"\'',
            id="logged commit read through a jq program built from a variable",
        ),
        pytest.param("gh api repos/furedea/agent-config/issues/comments/$id --jq .body", id="logged comment read"),
        pytest.param("gh api repos/furedea/template-typescript/contents/$f --jq .content", id="logged file read"),
        pytest.param("gh run list --commit $sha", id="an unquoted commit"),
        pytest.param("sha=0123; gh run list --commit $sha", id="a commit assigned on the line"),
        pytest.param("gh pr view $(cat number.txt)", id="a PR number from a substitution"),
        pytest.param("gh pr view 1 --repo other/r --comments", id="a PR of another owner"),
        pytest.param("gh search repos agent --owner furedea", id="a repository search"),
        pytest.param("gh api -X GET search/issues -f q='repo:o/r is:open'", id="a GET with query fields"),
        pytest.param("gh api user", id="a plain REST read"),
        pytest.param("gh api repos/o/r/actions/runs --paginate -H 'Accept: application/json'", id="a header read"),
        pytest.param("gh pr checkout 12", id="a checkout, which changes only the local repository"),
        pytest.param("gh repo clone furedea/agent-config", id="a clone"),
        pytest.param("gh stack init", id="an interactive stack init"),
        *(
            pytest.param(command, id=f"a header read {name}")
            for name, command in (
                ("after a semicolon", "true; gh api -H 'Accept: x' repos/o/r"),
                ("in a pipeline", "gh api -H 'Accept: x' repos/o/r | cat"),
                ("in the background", "gh api -H 'Accept: x' repos/o/r &"),
                ("in a subshell", "( gh api -H 'Accept: x' repos/o/r )"),
                ("through eval", "eval 'gh api -H \"Accept: x\" repos/o/r'"),
                ("through source", "source ./env.sh && gh api -H 'Accept: x' repos/o/r"),
                ("through env", "env gh api -H 'Accept: x' repos/o/r"),
                ("through sh -c", "sh -c 'gh api -H \"Accept: x\" repos/o/r'"),
                ("through timeout", "timeout 5 gh api -H 'Accept: x' repos/o/r"),
                ("with a redirect to a file", "gh api -H 'Accept: x' repos/o/r > out.txt"),
                ("with an assignment prefix", "X=1 gh api -H 'Accept: x' repos/o/r"),
            )
        ),
    ],
)
def test_reads_and_local_changes_are_allowed_in_any_form(command: str) -> None:
    assert decide(command) == "allow"


@pytest.mark.usefixtures("furedea_checkout")
@pytest.mark.parametrize(
    ("command", "fragment"),
    [
        pytest.param(
            "gh issue comment ${url##*/} --body-file /tmp/plan_types.md",
            "may become an option",
            id="logged comment on an issue number cut from a URL",
        ),
        pytest.param(
            'gh api graphql -f query="{node(id:\\"PRRT_kwDOVVcfb863$t\\"){id}}" --jq .data',
            "literal query",
            id="logged GraphQL document built at run time",
        ),
        pytest.param(
            "gh api repos/furedea/template-minimal/git/trees/HEAD?recursive=1 --jq '.tree[].path'",
            "split",
            id="logged endpoint holding an unquoted glob",
        ),
        pytest.param("gh pr create --repo other/r --title x --body y", "class C", id="another owner by option"),
        pytest.param("gh issue comment 1 -Rother/r -b ok", "class C", id="another owner in a short bundle"),
        pytest.param("gh pr comment https://github.com/other/r/pull/1 -b x", "class C", id="another owner by URL"),
        pytest.param("gh pr comment https://ghe.example/furedea/r/pull/1 -b x", "class C", id="another host by URL"),
        pytest.param("gh issue comment 1 -R ghe.example/furedea/r -b x", "class C", id="another host by option"),
        pytest.param("gh issue develop 1 --branch-repo other/r", "class C", id="a branch in another repository"),
        pytest.param('gh issue comment 1 -R "$R" -b x', "class C", id="a repository known only at run time"),
        pytest.param("gh api repos/other/r/issues/1/comments -f body=x", "class C", id="another owner by REST"),
        pytest.param(
            "gh api --hostname ghe.example repos/furedea/r/issues/1/comments -f body=x",
            "class C",
            id="another host by REST",
        ),
        pytest.param(
            "gh api -X POST repos/furedea/../issues -f title=x", "dot segment", id="a dot segment in a REST path"
        ),
        pytest.param(
            f"gh api --hostname ghe.example graphql -f query='mutation{{{RESOLVE}}}'",
            "class C",
            id="an allowlisted mutation on another host",
        ),
        pytest.param("cd ../elsewhere && gh issue comment 1 -b x", "class C", id="a directory change before"),
        pytest.param("GH_REPO=other/r gh issue comment 1 -b x", "class C", id="GH_REPO on the line"),
        pytest.param("env GH_REPO=other/r gh issue comment 1 -b x", "class C", id="GH_REPO through env"),
        pytest.param("timeout 9 gh issue comment 1 -b x", "class C", id="a wrapper hiding the environment"),
        pytest.param("gh pr review 42 --approve", "class D", id="an approval"),
        pytest.param("gh pr review 42 -ca", "class D", id="an approval in a short bundle"),
        pytest.param("gh pr close 42 -d", "class D", id="a close that deletes the branch"),
        pytest.param("gh pr comment 42 --delete-last --yes", "class D", id="a comment deletion"),
        pytest.param("gh api -X DELETE repos/furedea/r/issues/comments/1", "class D", id="a REST deletion"),
        pytest.param("gh api -X PUT repos/furedea/r/pulls/1/merge", "class D", id="a REST merge"),
        pytest.param("gh api -X PATCH repos/furedea/r -f private=false", "class D", id="a repository setting"),
        pytest.param("gh api repos/furedea/r/releases -f tag_name=v1", "class D", id="a REST release"),
        pytest.param(
            "gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
            "class D",
            id="a mutation outside the allowlist",
        ),
        pytest.param(
            f"gh api graphql -f query='mutation{{a:{RESOLVE} "
            'b:deleteIssue(input:{issueId:"x"}){clientMutationId}}\'',
            "class D",
            id="an allowlisted mutation beside another",
        ),
        pytest.param("gh label delete bug", "operation table", id="a subcommand outside the table"),
        pytest.param("gh run delete 1", "operation table", id="a run deletion"),
        pytest.param('gh pr edit "$N" --body x', "may become an option", id="a quoted run-time number"),
        pytest.param("gh pr edit 1 $OPTS", "may become an option", id="run-time options"),
        pytest.param("gh pr create --foo x", "operation table", id="an option outside the table"),
        pytest.param("gh pr create --title", "no value", id="an option without its value"),
        pytest.param('gh pr create --body "$BODY"', "parameter expansion", id="a body from a parameter"),
        pytest.param('gh issue create --title "fix: $X" -b y', "parameter expansion", id="a title from a parameter"),
        pytest.param("X='1 -R o/r'; gh pr edit 1 --body-file $X", "split", id="a body file assigned on the line"),
        pytest.param("echo 1 | xargs gh pr close", "xargs", id="arguments from xargs"),
        pytest.param(
            "idx='pipestatus[1$(gh pr merge 1)]'; gh pr view \"$HOME[idx]\"",
            "zsh",
            id="a zsh subscript that runs hidden code",
        ),
    ],
)
def test_writes_that_widen_authority_promote_or_hide_their_target_ask(command: str, fragment: str) -> None:
    verdict = guard.decide("allowed", {"tool_input": {"command": command}})
    assert verdict.decision == "ask"
    assert fragment in verdict.reason


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
        pytest.param({}, "ask", id="no remote"),
    ],
)
@pytest.mark.usefixtures("isolated_project")
def test_a_write_to_the_working_repository_follows_every_github_remote(remotes: dict[str, str], expected: str) -> None:
    subprocess.run(["git", "init", "--quiet"], check=True)
    for name, url in remotes.items():
        add_remote(name, url)
    assert decide("gh issue comment 1 -b ok") == expected


@pytest.mark.usefixtures("furedea_checkout")
def test_gh_repo_in_the_hook_environment_names_the_working_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_REPO", "other/r")
    assert decide("gh issue comment 1 -b ok") == "ask"


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
        pytest.param("gh api graphql -f query='{ viewer { login } }' -F note=@body.md", id="a file in a read"),
    ],
)
def test_a_secret_in_a_literal_file_the_call_sends_asks(secret_samples: dict[str, str], command: str) -> None:
    Path("body.md").write_text(f"config = {secret_samples['aws_key']}\n")
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_secret_in_a_heredoc_body_asks(secret_samples: dict[str, str]) -> None:
    command = f"gh issue comment 1 --body-file - <<'EOF'\n{secret_samples['github_token']}\nEOF"
    assert decide(command) == "ask"


@pytest.mark.usefixtures("furedea_checkout")
def test_a_body_file_without_secrets_is_allowed() -> None:
    Path("body.md").write_text("## Summary\n\nNo secrets here.\n")
    assert decide("gh pr create --head x -t y --body-file body.md") == "allow"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"version": 2, "grants": [], "commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [{"target": "any", "effects": ["read"], "decision": "allow"}], '
        '"commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [{"target": "anyone", "effects": ["read"], "decision": "allow", '
        '"justification": "x"}], "commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [], "commands": {"pr view": {"operation": "pr.view", "effect": "maybe"}}, '
        '"rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [], "commands": {}, "rest": [{"method": "POST", "path": "repos/*", '
        '"operation": "x.y", "effect": "reversible"}], "graphql_mutations": {}}',
    ],
    ids=["not JSON", "a newer version", "no justification", "an unknown target", "an unknown effect", "a bad path"],
)
def test_a_malformed_policy_table_blocks_instead_of_widening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    path = tmp_path / "gh_policy.json"
    path.write_text(content)
    monkeypatch.setenv("AGENT_GH_POLICY", str(path))
    verdict = guard.decide("allowed", {"tool_input": {"command": "gh pr list"}})
    assert verdict.decision == "deny"
    assert "invalid gh policy" in verdict.reason
