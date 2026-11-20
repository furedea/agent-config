"""Judge `t3 thread` calls, which run outside the sandbox and hand work to another agent.

A lane starts only on an explicitly named Claude or Codex instance: without `--provider` T3 uses
the project's default, which may be Antigravity, and Antigravity must never be driven by another
agent on a subscription. Every other form must keep to the documented options so that no word can
change the data directory, the provider, or the target unseen. Whether a send targets a thread
this session started is the session's ownership check (`t3_ownership`).
"""

from dataclasses import dataclass
from pathlib import Path

import hook_decision
import shell_syntax
from hook_decision import Verdict

PROGRAM = "t3"
PROVIDERS = frozenset({"claudeAgent", "codex"})
PROVIDER_REASON = (
    "BLOCKED: a T3 thread must name its provider instance: --provider claudeAgent or --provider codex, "
    "with --model. Without it T3 uses the project default, which may be Antigravity, and no other "
    "agent may drive Antigravity.\n\nCommand: {preview}\n\n" + hook_decision.REVIEW_HINT
)


@dataclass(frozen=True, slots=True)
class Grammar:
    """The documented options and positional count of one `t3 thread` action."""

    valued: frozenset[str]
    flags: frozenset[str]
    positionals: int


GRAMMARS = {
    "start": Grammar(
        frozenset({"--title", "--provider", "--model", "--worktree", "--branch"}), frozenset({"--wait", "--json"}), 2
    ),
    "send": Grammar(frozenset(), frozenset({"--wait", "--json"}), 2),
    "show": Grammar(frozenset({"--messages"}), frozenset({"--json"}), 1),
    "list": Grammar(frozenset({"--project"}), frozenset({"--json"}), 0),
}


@dataclass(frozen=True, slots=True)
class ThreadCall:
    """A `t3 thread` call read word by word; a positional known only at run time is None."""

    action: str
    options: tuple[tuple[str, str], ...]
    positionals: tuple[str | None, ...]

    def values(self, name: str) -> list[str]:
        """Every value given for one option, in order; a flag's value is empty."""
        return [value for option, value in self.options if option == name]

    @property
    def target(self) -> str | None:
        """The thread a send or show names, as T3 reads it, or None when it is known only at run time."""
        thread = self.positionals[0]
        return None if thread is None else thread.strip()


@dataclass(frozen=True, slots=True)
class Unreadable:
    """A `t3 thread` call whose effect the guard cannot read from its words."""

    reason: str


def refusal(commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Deny a thread start that does not name only allowed provider instances, wherever it runs."""
    for item in commands:
        words = _thread_words(item)
        if words is None or words[:1] != ("start",):
            continue
        providers = _provider_values(item, len(item.arguments) - len(words) + 1)
        if not providers or not {value for value in providers if value is not None} <= PROVIDERS:
            preview = shell_syntax.command_preview(item.raw)
            return hook_decision.deny(PROVIDER_REASON.format(preview=preview), "t3 thread start")
    return hook_decision.ALLOW


def objection(commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask for a `t3 thread` call outside the documented, directly run forms."""
    for item in commands:
        words = _thread_words(item)
        if words is None:
            continue
        problem = _direct_problem(item) or _form_problem(read(item))
        if problem:
            preview = shell_syntax.command_preview(item.raw)
            return hook_decision.ask(f"Needs review: {problem}.\n\nCommand: {preview}", "t3 thread")
    return hook_decision.ALLOW


def read(item: shell_syntax.Command) -> ThreadCall | Unreadable | None:
    """The `t3 thread` call a command makes, or None when it makes none."""
    if _thread_words(item) is None:
        return None
    if item.arguments[1] != "thread" or len(item.arguments) < 3:
        return Unreadable("t3 options before the thread subcommand shift its words")
    action = item.arguments[2]
    grammar = GRAMMARS.get(action)
    if grammar is None:
        return Unreadable(f"t3 thread {action} is not a lane command")
    return _parse(item, action, grammar)


def _parse(item: shell_syntax.Command, action: str, grammar: Grammar) -> ThreadCall | Unreadable:
    options: list[tuple[str, str]] = []
    positionals: list[str | None] = []
    index = 3
    words = list(zip(item.arguments, item.dynamic, item.spreading, strict=True))
    while index < len(words):
        word, dynamic, spreading = words[index]
        index += 1
        if spreading:
            return Unreadable("a word may split into options at run time")
        if dynamic or word == "-" or not word.startswith("-"):
            positionals.append(None if dynamic else word)
            continue
        name, separator, attached = word.partition("=")
        if name in grammar.flags and not separator:
            options.append((name, ""))
            continue
        if name not in grammar.valued:
            return Unreadable(f"option {name} of t3 thread {action} needs the user's judgment")
        value = attached if separator else _next_value(words[index : index + 1], name)
        index += 0 if separator else 1
        if isinstance(value, Unreadable):
            return value
        options.append((name, value))
    if len(positionals) != grammar.positionals:
        return Unreadable(f"t3 thread {action} takes {grammar.positionals} words besides its options")
    return ThreadCall(action, tuple(options), tuple(positionals))


def _next_value(words: list[tuple[str, bool, bool]], name: str) -> str | Unreadable:
    """The literal word after a valued option; an option or a run-time word there cannot be read as its value."""
    if not words:
        return Unreadable(f"option {name} has no value")
    value, dynamic, spreading = words[0]
    if dynamic or spreading or value.startswith("-"):
        return Unreadable(f"the value of {name} is an option or known only at run time")
    return value


def _form_problem(call: ThreadCall | Unreadable | None) -> str:
    if isinstance(call, Unreadable):
        return call.reason
    if call is None:
        return ""
    names = [name for name, _ in call.options]
    if len(names) != len(set(names)):
        return "an option given twice may be read either way"
    if call.action == "start" and not (call.values("--provider") and call.values("--model")):
        return "a thread start needs --provider claudeAgent or codex together with --model"
    if call.action == "start" and not set(call.values("--provider")) <= PROVIDERS:
        return "a thread start may name only the claudeAgent or codex provider instance"
    return ""


def _direct_problem(item: shell_syntax.Command) -> str:
    if item.wrapper_depth:
        return "a t3 thread call behind a wrapper or inside a script hides its form from the permission rules"
    if item.assignments:
        return "an environment assignment can move T3 to another data directory or server"
    return ""


def _thread_words(item: shell_syntax.Command) -> tuple[str, ...] | None:
    """The words after the first `thread` of a t3 call, or None when the command is no t3 thread call."""
    if not item.arguments or item.program_is_dynamic or Path(item.arguments[0]).name != PROGRAM:
        return None
    arguments = item.arguments[1:]
    return arguments[arguments.index("thread") + 1 :] if "thread" in arguments else None


def _provider_values(item: shell_syntax.Command, start: int) -> list[str | None]:
    """Every `--provider` value after the action word; a value known only at run time is None."""
    values: list[str | None] = []
    arguments = item.arguments
    for index in range(start, len(arguments)):
        word = arguments[index]
        if word.startswith("--provider="):
            values.append(None if item.dynamic[index] else word.partition("=")[2])
        elif word == "--provider" and index + 1 < len(arguments):
            values.append(None if item.dynamic[index + 1] else arguments[index + 1])
    return values
