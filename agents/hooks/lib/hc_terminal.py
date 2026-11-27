"""Judge `hc` (herdr-core) calls, which run outside the sandbox and can hand work to another agent.

A lane starts only Claude or Codex, with the options the guard lists: any other option can switch off
the agent's sandbox, hooks, or approvals, so passing one is refused. Every other form must keep to the
documented options so that no word can change the core, the machine, or the target unseen. Whether a
send, kill, or rm targets a terminal this session started is the session's ownership check
(`hc_ownership`).
"""

from dataclasses import dataclass
from pathlib import Path

import hook_decision
import literal_words
import shell_syntax
from hook_decision import Verdict

PROGRAM = "hc"
INFO_FORMS = frozenset({("--help",), ("--version",), ("-V",), ("--skill",)})
AGENT_REASON = (
    "BLOCKED: an agent hc starts takes only --model and --effort (Claude) or --no-daemon and --model (Codex) "
    "besides its brief; any other option could switch off its sandbox, hooks, or approvals.\n\n"
    "Command: {preview}\n\n" + hook_decision.REVIEW_HINT
)


@dataclass(frozen=True, slots=True)
class Grammar:
    """The documented options, required options, and positional count range of one command."""

    valued: frozenset[str]
    flags: frozenset[str]
    positionals: tuple[int, int]
    required: frozenset[str] = frozenset()


RUN = Grammar(
    frozenset({"--name", "--cwd", "--label"}),
    frozenset({"--bg", "--json", "--no-parent"}),
    (1, 1 << 16),
    frozenset({"--bg", "--json", "--no-parent", "--name"}),
)
GRAMMARS = {
    "run": RUN,
    "send": Grammar(frozenset(), frozenset({"--json"}), (2, 2)),
    "get": Grammar(frozenset(), frozenset({"--json"}), (1, 1)),
    "read": Grammar(frozenset({"--lines"}), frozenset({"--json"}), (1, 1)),
    "wait": Grammar(frozenset({"--timeout"}), frozenset({"--json"}), (1, 1)),
    "ls": Grammar(frozenset(), frozenset({"--json", "--all"}), (0, 0)),
    "kill": Grammar(frozenset(), frozenset({"--json"}), (1, 1)),
    "rm": Grammar(frozenset(), frozenset({"--json"}), (1, 1)),
    "templates": Grammar(frozenset(), frozenset({"--json"}), (0, 0)),
}
AGENTS = {
    "claude": Grammar(frozenset({"--model", "--effort"}), frozenset(), (1, 1)),
    "codex": Grammar(frozenset({"--model"}), frozenset({"--no-daemon"}), (1, 1), frozenset({"--no-daemon"})),
}
OWNED_ACTIONS = frozenset({"send", "kill", "rm"})


@dataclass(frozen=True, slots=True)
class TerminalCall:
    """An `hc` call read word by word; a positional known only at run time is None."""

    action: str
    options: tuple[tuple[str, str], ...]
    positionals: tuple[str | None, ...]

    def values(self, name: str) -> list[str]:
        """Every value given for one option, in order; a flag's value is empty."""
        return [value for option, value in self.options if option == name]

    @property
    def target(self) -> str | None:
        """The terminal a send, kill, or rm names, or None when it is known only at run time."""
        return self.positionals[0] if self.positionals else None


@dataclass(frozen=True, slots=True)
class Unreadable:
    """An `hc` call whose effect the guard cannot read from its words."""

    reason: str


def refusal(commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Deny an `hc run` that passes Claude or Codex an option outside their lane options, wherever it runs."""
    for item in commands:
        words = _hc_words(item)
        if words is None or words[:1] != ("run",):
            continue
        agent = _agent_words(words[1:])
        if not agent or Path(agent[0]).name not in AGENTS:
            continue
        grammar = AGENTS[Path(agent[0]).name]
        options = agent[1 : agent.index("--")] if "--" in agent else agent[1:]
        if any(_unlisted_option(word, grammar) for word in options):
            preview = shell_syntax.command_preview(item.raw)
            return hook_decision.deny(AGENT_REASON.format(preview=preview), "hc run")
    return hook_decision.ALLOW


def objection(command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask for an `hc` call outside the documented, directly run, literal forms.

    The whole line of an excluded command runs outside the sandbox, so a substitution in any word,
    or another command in the line, would run there too.
    """
    literal = literal_words.allows_literal_rules(command, commands) and all(
        _hc_words(item) is not None or literal_words.is_read_only_filter(item) for item in commands
    )
    for item in commands:
        if _hc_words(item) is None:
            continue
        call = read(item)
        problem = (
            _direct_problem(item) or _form_problem(call) or _line_problem(call, literal, alone=len(commands) == 1)
        )
        if problem:
            preview = shell_syntax.command_preview(item.raw)
            return hook_decision.ask(f"Needs review: {problem}.\n\nCommand: {preview}", "hc")
    return hook_decision.ALLOW


def read(item: shell_syntax.Command) -> TerminalCall | Unreadable | None:
    """The `hc` call a command makes, or None when it makes none."""
    words = _hc_words(item)
    if words is None:
        return None
    if words in INFO_FORMS or (len(words) == 2 and words[0] in GRAMMARS and words[1] == "--help"):
        return TerminalCall("info", (), ())
    if not words or words[0].startswith("-"):
        return Unreadable("hc options before the subcommand shift its words")
    grammar = GRAMMARS.get(words[0])
    if grammar is None:
        return Unreadable(f"hc {words[0]} is not a lane command")
    return _parse(item, words[0], grammar)


def _parse(item: shell_syntax.Command, action: str, grammar: Grammar) -> TerminalCall | Unreadable:
    options: list[tuple[str, str]] = []
    positionals: list[str | None] = []
    words = list(zip(item.arguments, item.dynamic, item.spreading, strict=True))
    index = 2
    while index < len(words):
        word, dynamic, spreading = words[index]
        if spreading:
            return Unreadable("a word may split into options at run time")
        index += 1
        if action == "run" and (dynamic or word == "--" or not word.startswith("-")):
            return _run_call(options, words[index - 1 :])
        if dynamic or word == "-" or not word.startswith("-"):
            positionals.append(None if dynamic else word)
            continue
        name, separator, attached = word.partition("=")
        if name in grammar.flags and not separator:
            options.append((name, ""))
            continue
        if name not in grammar.valued:
            return Unreadable(f"option {name} of hc {action} needs the user's judgment")
        value = attached if separator else _next_value(words[index : index + 1], name)
        index += 0 if separator else 1
        if isinstance(value, Unreadable):
            return value
        options.append((name, value))
    low, high = grammar.positionals
    if not low <= len(positionals) <= high:
        return Unreadable(f"hc {action} takes {low} to {high} words besides its options")
    return TerminalCall(action, tuple(options), tuple(positionals))


def _run_call(options: list[tuple[str, str]], words: list[tuple[str, bool, bool]]) -> TerminalCall | Unreadable:
    """An `hc run` call whose remaining words, after one optional `--`, are the agent's argv."""
    if words[0][0] == "--" and not words[0][1]:
        words = words[1:]
    if any(spreading for _, _, spreading in words):
        return Unreadable("a word may split into options at run time")
    if not words:
        return Unreadable("hc run names no program")
    return TerminalCall("run", tuple(options), tuple(None if dynamic else word for word, dynamic, _ in words))


def _next_value(words: list[tuple[str, bool, bool]], name: str) -> str | Unreadable:
    """The literal word after a valued option; an option or a run-time word there cannot be read as its value."""
    if not words:
        return Unreadable(f"option {name} has no value")
    value, dynamic, spreading = words[0]
    if dynamic or spreading or value.startswith("-"):
        return Unreadable(f"the value of {name} is an option or known only at run time")
    return value


def _form_problem(call: TerminalCall | Unreadable | None) -> str:
    if isinstance(call, Unreadable):
        return call.reason
    if call is None or call.action == "info":
        return ""
    return _option_problem(call) or _argument_problem(call)


def _option_problem(call: TerminalCall) -> str:
    names = [name for name, _ in call.options if name != "--label"]
    if len(names) != len(set(names)):
        return "an option given twice may be read either way"
    missing = GRAMMARS[call.action].required - set(names)
    if missing:
        return "an hc run lane needs --bg, --no-parent, --json, and --name: " + ", ".join(sorted(missing)) + " missing"
    return ""


def _argument_problem(call: TerminalCall) -> str:
    if call.action == "run":
        return _agent_problem(call.positionals)
    if call.action == "send" and not call.positionals[1]:
        return "a send needs a literal message"
    return ""


def _agent_problem(argv: tuple[str | None, ...]) -> str:
    """Why the program an `hc run` starts is not a lane agent in a form the guard reads."""
    program = argv[0]
    if program not in AGENTS:
        return "hc run starts only claude or codex by name; another program or a template runs unseen"
    grammar = AGENTS[program]
    read_options = _agent_options(program, grammar, argv[1:])
    if isinstance(read_options, str):
        return read_options
    options, positionals = read_options
    if len(options) != len(set(options)):
        return f"an option of {program} given twice may be read either way"
    if not grammar.required <= set(options):
        required = ", ".join(sorted(grammar.required))
        return f"{program} must run with {required}, or its commands execute outside hc"
    if positionals != 1:
        return f"{program} takes exactly one brief message besides its options"
    return ""


def _agent_options(program: str, grammar: Grammar, argv: tuple[str | None, ...]) -> tuple[list[str], int] | str:
    """The agent options named and the count of other words, or why a word cannot be read."""
    options: list[str] = []
    positionals = 0
    words = iter(argv)
    for word in words:
        if word is None or not word.startswith("-"):
            positionals += 1
            continue
        name, separator, _ = word.partition("=")
        if name not in grammar.valued | grammar.flags or (name in grammar.flags and separator):
            return f"option {word} of {program} needs the user's judgment"
        value = "" if separator or name in grammar.flags else next(words, None)
        if value is None or value.startswith("-"):
            return f"option {name} of {program} has no literal value"
        options.append(name)
    return options, positionals


def _line_problem(call: TerminalCall | Unreadable | None, literal: bool, *, alone: bool) -> str:
    """Why the line around a readable call cannot run unprompted: it must be literal, and a start recordable."""
    if not literal:
        return "the line runs outside the sandbox, so it must be literal hc calls only"
    if isinstance(call, TerminalCall) and call.action == "run" and not alone:
        return "only one plain hc run --json records its terminal, so this session could not message it"
    return ""


def _direct_problem(item: shell_syntax.Command) -> str:
    if item.wrapper_depth:
        return "an hc call behind a wrapper or inside a script hides its form from the permission rules"
    if item.assignments:
        return "an environment assignment can move hc to another core"
    if item.redirections:
        return "a redirect of an unsandboxed hc call can read or write any file"
    return ""


def _hc_words(item: shell_syntax.Command) -> tuple[str, ...] | None:
    """The words after `hc`, or None when the command is no hc call."""
    if not item.arguments or item.program_is_dynamic or Path(item.arguments[0]).name != PROGRAM:
        return None
    return tuple(item.arguments[1:])


def _agent_words(words: tuple[str, ...]) -> tuple[str, ...]:
    """The agent's argv in `hc run` words: everything from the first word that is no hc option or its value."""
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            return words[index + 1 :]
        if not word.startswith("-"):
            return words[index:]
        index += 2 if word in RUN.valued else 1
    return ()


def _unlisted_option(word: str, grammar: Grammar) -> bool:
    name = word.partition("=")[0]
    return word.startswith("-") and name not in grammar.valued | grammar.flags
