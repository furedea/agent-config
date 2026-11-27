"""hc lanes start only Claude or Codex with options the guard can read, and every hc call runs outside the sandbox."""

import json

import pytest
from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")
RUN = "hc run --bg --no-parent --json --name lane-a --cwd /wt/lane-a --label herdr.space=repo --label herdr.tab=lane-a"


def verdict(command: str) -> str:
    """The combined decision of the forbidden and allowed guards, as a provider merges them."""
    decisions = {
        guard.decide(kind, {"tool_input": {"command": command}}).decision for kind in ("forbidden", "allowed")
    }
    return next(decision for decision in ("deny", "ask", "allow") if decision in decisions)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"{RUN} claude --model sonnet --effort medium 'Read /tmp/brief.md'", id="a Claude lane"),
        pytest.param(f"{RUN} claude 'Read /tmp/brief.md'", id="a Claude lane on its defaults"),
        pytest.param(f"{RUN} codex --no-daemon --model gpt-6.1-sol 'Read /tmp/brief.md'", id="a Codex reviewer"),
        pytest.param(f"{RUN} -- claude 'Read /tmp/brief.md'", id="an end of hc options before the agent"),
        pytest.param("hc run --name=lane-a --bg --no-parent --json claude hi", id="a name with ="),
        pytest.param("hc send t7 'Address the review'", id="a message to a terminal"),
        pytest.param("hc get t7 --json", id="a terminal read"),
        pytest.param("hc read t7 --lines 200", id="a screen read"),
        pytest.param("hc wait t7 --timeout 1800 --json", id="a wait"),
        pytest.param("hc ls --all --json", id="a listing"),
        pytest.param("hc ls --json | jq .", id="a listing through a read-only filter"),
        pytest.param("hc kill t7", id="ending a terminal"),
        pytest.param("hc rm t7", id="removing a finished terminal"),
        pytest.param("hc templates", id="the templates"),
        pytest.param("hc --skill", id="the agent manual"),
        pytest.param("hc --version", id="the version"),
        pytest.param("hc run --help", id="a subcommand's help"),
    ],
)
def test_lane_forms_run_without_approval(command: str) -> None:
    assert verdict(command) == "allow"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"{RUN} claude --dangerously-skip-permissions hi", id="Claude without approvals"),
        pytest.param(f"{RUN} claude --permission-mode bypassPermissions hi", id="a Claude permission mode"),
        pytest.param(f"{RUN} claude --settings /tmp/s.json hi", id="other Claude settings"),
        pytest.param(f"{RUN} claude --model=sonnet --allowedTools Bash hi", id="a Claude tool list"),
        pytest.param(f"{RUN} codex --no-daemon --yolo hi", id="Codex without its sandbox"),
        pytest.param(f"{RUN} codex --no-daemon -c sandbox_mode=danger-full-access hi", id="a Codex config override"),
        pytest.param(f"{RUN} /usr/local/bin/claude -p hi", id="Claude by path"),
        pytest.param(f"env FOO=1 {RUN} claude --dangerously-skip-permissions hi", id="behind a wrapper"),
        pytest.param(f"bash -c '{RUN} codex --yolo hi'", id="inside a shell script"),
    ],
)
def test_an_agent_option_that_can_switch_off_its_safeguards_is_refused(command: str) -> None:
    result = guard.decide("forbidden", {"tool_input": {"command": command}})
    assert result.decision == "deny"
    assert "--model" in result.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(f"{RUN} bash -c 'rm -rf ~'", id="another program"),
        pytest.param(f"{RUN} reviewer 'Review x.rs'", id="a template, whose command the guard cannot see"),
        pytest.param(f"{RUN} codex 'Read /tmp/brief.md'", id="Codex without --no-daemon runs outside hc"),
        pytest.param(f"{RUN} claude", id="an agent without its brief"),
        pytest.param(f"{RUN} claude hi extra", id="an extra word"),
        pytest.param(f"{RUN} claude --model hi", id="an option without a value"),
        pytest.param(f"{RUN} claude --model sonnet --model opus hi", id="an agent option given twice"),
        pytest.param(f"{RUN} claude -- hi", id="an end of agent options"),
        pytest.param("hc run --no-parent --json --name lane-a claude hi", id="a run that streams into this call"),
        pytest.param("hc run --bg --json --name lane-a claude hi", id="a lane that ends with its parent"),
        pytest.param("hc run --bg --no-parent --name lane-a claude hi", id="a start whose terminal is not recorded"),
        pytest.param("hc run --bg --no-parent --json claude hi", id="a lane without a name"),
        pytest.param(f"{RUN} --on vps claude hi", id="another machine"),
        pytest.param(f"{RUN} --keep claude hi", id="an unknown hc option"),
        pytest.param(f"{RUN} --name lane-b claude hi", id="an hc option given twice"),
        pytest.param(f"HC_SESSION=/tmp/x {RUN} claude hi", id="another core"),
        pytest.param(f'{RUN} claude "$(cat /tmp/brief.md)"', id="a substitution the unsandboxed shell would run"),
        pytest.param(f"{RUN} claude $PROMPT", id="words split at run time"),
        pytest.param(f"{RUN} claude hi | cat", id="a start through a filter"),
        pytest.param(f"hc ls && {RUN} claude hi", id="a start in a list"),
        pytest.param("cp /etc/passwd /tmp/leak; hc ls", id="a list the unsandboxed shell would run"),
        pytest.param("hc ls --json > /home/user/.bashrc", id="a write outside the sandbox"),
        pytest.param("gh pr list && hc ls", id="another unsandboxed program in the line"),
        pytest.param("hc send t7 'hi' --force", id="typing into a blocked agent"),
        pytest.param("hc send t7", id="a send without a message"),
        pytest.param("hc wait", id="a wait that picks its terminal"),
        pytest.param("hc --json ls", id="an option before the subcommand"),
        pytest.param("hc exec 'rm -rf ~'", id="a command outside any terminal"),
        pytest.param("hc file write /etc/hosts", id="a file write"),
        pytest.param("hc keys t7 enter", id="raw keys"),
        pytest.param("hc interrupt t7", id="an interrupt"),
        pytest.param("hc attach t7", id="an attach"),
        pytest.param("hc machine add box", id="a machine"),
        pytest.param("hc server stop", id="the server"),
        pytest.param("hc update", id="an update"),
    ],
)
def test_forms_the_guard_cannot_read_need_review(command: str) -> None:
    assert verdict(command) == "ask"


@pytest.mark.parametrize(
    "command",
    ["echo hc run --bg claude --yolo", "git commit -m 'hc run claude --yolo'", "hc ls"],
    ids=["an echo", "a commit message", "a listing"],
)
def test_text_and_other_hc_subcommands_are_not_judged_as_an_agent_start(command: str) -> None:
    assert guard.decide("forbidden", {"tool_input": {"command": command}}).decision == "allow"


def test_hc_leaves_the_claude_sandbox() -> None:
    sandbox = json.loads((REPO_ROOT / "agents/claude/settings.json").read_text())["sandbox"]
    assert [command for command in sandbox["excludedCommands"] if command.startswith("hc ")] == ["hc *"]


def test_only_the_lane_commands_have_allowing_permission_prefixes() -> None:
    rules = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]
    allowed = {tuple(rule["prefix"]) for rule in rules if rule["prefix"][0] == "hc" and rule["decision"] == "allow"}
    lane = ("run", "send", "get", "read", "wait", "ls", "kill", "rm", "templates", "--help", "--version", "--skill")
    assert allowed == {("hc", action) for action in lane}
