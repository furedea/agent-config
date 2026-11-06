"""Commands that skills and AGENTS.md tell an agent to run get the verdict the command hooks would give them.

The verdicts come from the hook's own functions, so the policy is never restated here. The commands
that are meant to be denied, or to wait for approval, are listed with a reason in
skill_command_expectations.json; every other command must run without approval.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import textwrap

import pytest

from tests.runtime import REPO_ROOT, load_script_module


SOURCES = (REPO_ROOT / "agents/AGENTS.md", *sorted((REPO_ROOT / "agents/skills").rglob("*.md")))
EXPECTATIONS = json.loads(Path(__file__).with_name("skill_command_expectations.json").read_text())
FENCE = re.compile(r"^( *)```(?:bash|sh|shell|console)[^\n]*\n(.*?)^\1```", re.MULTILINE | re.DOTALL)
PLACEHOLDER = re.compile(r"<[A-Za-z][\w -]*>|\{[A-Za-z_][\w-]*\}")
# A block that is a script, a function, a loop, or a bats test is not a list of commands to run one by one.
SCRIPT = re.compile(r"\A#!|\w+\(\) *\{|^\s*(?:for|while|if|case|run|@test) ", re.MULTILINE)
FORBIDDEN_PHRASES = re.compile(
    r"@latest|\buv pip\b|\bpip install\b|(?<!p)npm install\b|\buv run (?:--no-project )?(?:pytest|ruff|ty)\b"
)
# The hooks' answers each expectation accepts: a command that no allow prefix lists waits for approval too.
ACCEPTED = {"allow": {"allow"}, "forbidden": {"deny"}, "needs-approval": {"ask", "unregistered"}, "not-command": set()}


@dataclass(frozen=True, slots=True)
class SkillCommand:
    path: str
    text: str
    is_script: bool


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def skill_commands(source: Path) -> list[SkillCommand]:
    """One command per line of each fenced shell block; a block with a heredoc is one command."""
    commands = []
    for _, block in FENCE.findall(source.read_text()):
        block = textwrap.dedent(block)
        lines = [block.strip()] if "<<" in block else block.replace("\\\n", " ").splitlines()
        texts = (re.sub(r"^\$ ", "", line.strip()) for line in lines)
        commands += [
            SkillCommand(relative(source), text, bool(SCRIPT.search(block)))
            for text in texts
            if text[:1] not in {"", "#"}
        ]
    return commands


def all_commands() -> list[SkillCommand]:
    return [command for source in SOURCES for command in skill_commands(source)]


def expectation(command: SkillCommand) -> str:
    """What the expectations file says about this command, or allow."""
    return next(
        (entry["expect"] for entry in EXPECTATIONS if (entry["path"], entry["text"]) == (command.path, command.text)),
        "allow",
    )


class Hooks:
    """The command hooks' verdicts: deny, ask, allow, or unregistered when no allow prefix lists the command."""

    def __init__(self) -> None:
        replay = load_script_module("agents/hooks/replay_commands.py", "replay_commands")
        self.replayer = replay.Replayer(REPO_ROOT / "agents/hooks")
        self.recorded = replay.RecordedCommand
        self.command_policy = sys.modules["command_policy"]
        self.shell_syntax = sys.modules["shell_syntax"]
        self.prefixes = self.command_policy.load_rules(REPO_ROOT / "agents/command_permissions.json", prefixes=True)

    def verdict(self, command: SkillCommand) -> str:
        """A script's lines are judged for denial only, since a line alone is not a complete command."""
        text = PLACEHOLDER.sub("placeholder", command.text)
        decision = self.replayer.judge(self.recorded(text, str(REPO_ROOT))).decision
        if decision == "deny":
            return decision
        if command.is_script:
            return "allow"
        if decision == "ask":
            return decision
        arguments = [self.command_policy.canonical(item).arguments for item in self.shell_syntax.parse(text)]
        if any(self.has_prefix(words, "ask") for words in arguments):
            return "ask"
        return "allow" if all(self.has_prefix(words, "allow") for words in arguments) else "unregistered"

    def has_prefix(self, arguments: tuple[str, ...], decision: str) -> bool:
        return self.command_policy.prefix_rule(arguments, self.prefixes, decision) is not None


@pytest.fixture
def hooks(isolated_project: Path) -> Hooks:
    return Hooks()


def test_every_skill_command_gets_the_verdict_its_expectation_names(hooks: Hooks) -> None:
    mismatches = [
        f"{command.path}: {command.text}  ->  {verdict}, expected {expectation(command)}"
        for command in all_commands()
        if expectation(command) != "not-command"
        and (verdict := hooks.verdict(command)) not in ACCEPTED[expectation(command)]
    ]
    assert mismatches == []


def test_every_expectation_names_a_reason_and_text_that_is_still_in_its_file() -> None:
    commands = {(command.path, command.text) for command in all_commands()}
    broken = [
        entry
        for entry in EXPECTATIONS
        if not entry["reason"]
        or entry["expect"] not in ACCEPTED
        or (
            (entry["path"], entry["text"]) not in commands
            and entry["text"] not in (REPO_ROOT / entry["path"]).read_text()
        )
    ]
    assert broken == []


def test_skills_do_not_recommend_what_the_policy_forbids() -> None:
    exempt = [(e["path"], e["text"]) for e in EXPECTATIONS if e["expect"] in {"forbidden", "not-command"}]
    found = [
        f"{relative(source)}:{number}: {line.strip()}"
        for source in SOURCES
        for number, line in enumerate(source.read_text().splitlines(), 1)
        if FORBIDDEN_PHRASES.search(line)
        and not any(path == relative(source) and text in line for path, text in exempt)
    ]
    assert found == []
