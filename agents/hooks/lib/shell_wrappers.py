"""Locate the command a process wrapper runs, refusing any option it does not list."""

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Self

from shell_words import UnsupportedSyntax


# Shell options that take the next word as a value, which would hide where the -c script starts.
SHELL_VALUED_OPTIONS = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})
COMMAND_LOOKUP = frozenset({"-v", "-V"})
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
ASSIGNING_WRAPPERS = frozenset({"env", "sudo"})
# Process wrappers run their trailing arguments as a command. Each entry lists the flags without an
# operand and the options whose operand is the next token; unknown options are refused, not skipped.
WRAPPERS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "caffeinate": (frozenset({"-d", "-i", "-m", "-s", "-u"}), frozenset({"-t", "-w"})),
    "chrt": (
        frozenset(
            {"-a", "-b", "-d", "-f", "-i", "-o", "-r", "-R", "-m", "-v", "--all-tasks", "--batch", "--deadline"}
            | {"--fifo", "--idle", "--other", "--rr", "--reset-on-fork", "--max", "--verbose"}
        ),
        frozenset({"-T", "-P", "-D", "--sched-runtime", "--sched-period", "--sched-deadline"}),
    ),
    "command": (frozenset({"-p"}), frozenset()),
    "doas": (frozenset({"-L", "-n", "-s"}), frozenset({"-C", "-u"})),
    "env": (frozenset({"-i", "--ignore-environment", "-0", "--null"}), frozenset({"-u", "--unset", "-C", "--chdir"})),
    "exec": (frozenset({"-c", "-l"}), frozenset({"-a"})),
    "flock": (
        frozenset({"-s", "-x", "-u", "-n", "-o", "-F", "--shared", "--exclusive", "--unlock", "--nonblock", "--nb"})
        | frozenset({"--close", "--no-fork", "--verbose"}),
        frozenset({"-E", "-w", "-c", "--conflict-exit-code", "--timeout", "--wait", "--command"}),
    ),
    "nice": (frozenset(), frozenset({"-n", "--adjustment"})),
    "nohup": (frozenset(), frozenset()),
    "busybox": (frozenset(), frozenset()),
    "ionice": (frozenset({"-t", "--ignore"}), frozenset({"-c", "-n", "--class", "--classdata"})),
    "script": (
        frozenset({"-a", "-e", "-f", "-q", "-k", "-r", "--append", "--return", "--flush", "--force", "--quiet"}),
        frozenset(
            {"-c", "-E", "-I", "-O", "-B", "-T", "-m", "-o", "--command", "--echo", "--log-in", "--log-out"}
            | {"--log-io", "--log-timing", "--logging-format", "--output-limit"}
        ),
    ),
    "setsid": (frozenset({"-c", "-f", "-w", "--ctty", "--fork", "--wait"}), frozenset()),
    "stdbuf": (frozenset(), frozenset({"-i", "-o", "-e", "--input", "--output", "--error"})),
    "sudo": (
        frozenset(
            {"-n", "-S", "-E", "-H", "-k", "-b", "-B", "-P", "-A", "--non-interactive", "--stdin", "--set-home"}
        ),
        frozenset({"-u", "-g", "-p", "-C", "-T", "-U", "-r", "-t", "--user", "--group", "--prompt"}),
    ),
    "taskset": (frozenset({"-a", "-c", "--all-tasks", "--cpu-list"}), frozenset()),
    "time": (frozenset({"-p", "-l", "-h", "-a", "--portability"}), frozenset({"-o", "-f", "--output", "--format"})),
    "unbuffer": (frozenset({"-p"}), frozenset()),
    "timeout": (
        frozenset({"--preserve-status", "--foreground", "-v"}),
        frozenset({"-k", "--kill-after", "-s", "--signal"}),
    ),
    "watch": (
        frozenset(
            {"-b", "-c", "-C", "-d", "-e", "-g", "-p", "-r", "-t", "-w", "-x", "--beep", "--color", "--no-color"}
            | {"--differences", "--errexit", "--chgexit", "--precise", "--no-rerun", "--no-title", "--no-wrap"}
            | {"--exec"}
        ),
        frozenset({"-n", "-q", "--interval", "--equexit"}),
    ),
    "xargs": (
        frozenset({"-0", "-r", "-t", "-p", "-x", "-o", "--null", "--no-run-if-empty", "--verbose", "--interactive"}),
        frozenset(
            {"-n", "-I", "-L", "-P", "-s", "-d", "-E", "-a", "--max-args", "--replace", "--max-lines", "--max-procs"}
        ),
    ),
}
# Operands a wrapper takes before the command: timeout's duration, taskset's mask, chrt's priority, flock's lock.
LEADING_OPERANDS = {"chrt": 1, "flock": 1, "script": 1, "taskset": 1, "timeout": 1}
# Options whose operand is a script a shell runs; watch joins its words into one unless it has -x.
SCRIPT_OPTIONS = {"flock": ("-c", "--command"), "script": ("-c", "--command")}
EXEC_OPTIONS = ("-x", "--exec")
PRIORITY = re.compile(r"\+?[0-9]+")
# Short options whose value, if any, is the rest of the bundle: watch -dx is -d with the value x.
OPTIONAL_ATTACHED = {"watch": frozenset({"-d"})}


def wrapped_index(arguments: tuple[str, ...], dynamic: tuple[bool, ...] = ()) -> int | None:
    """Locate the command a process wrapper runs, or None when the call is not a wrapper invocation."""
    name = Path(arguments[0]).name
    if name not in WRAPPERS:
        return None
    scan = OptionScan(name, arguments, dynamic=dynamic).run()
    if scan.runs_script and name != "script":
        return None
    index = scan.index + scan.leading_operands()
    if index < len(arguments) and (index > scan.index or name == "chrt") and arguments[index] == "--":
        index += 1
    if index >= len(arguments) or (name == "script" and arguments[index].startswith("-")):
        return None
    return index


@dataclass(slots=True)
class OptionScan:
    """Walk a wrapper's leading options: where its operands start, and each option seen with its value.

    An option the wrapper does not list is refused, so it asks instead of being skipped.
    """

    name: str
    arguments: tuple[str, ...]
    index: int = 1
    seen: dict[str, str | None] = field(default_factory=dict)
    scripts: list[str | None] = field(default_factory=list)
    dynamic: tuple[bool, ...] = ()

    @property
    def flags(self) -> frozenset[str]:
        return WRAPPERS[self.name][0]

    @property
    def valued(self) -> frozenset[str]:
        return WRAPPERS[self.name][1]

    @property
    def runs_script(self) -> bool:
        """Whether the wrapper hands its command to a shell as a script, which shell_script reads."""
        if self.name == "watch":
            return not any(option in self.seen for option in EXEC_OPTIONS)
        return bool(self.scripts)

    def leading_operands(self) -> int:
        """How many operands precede the command; chrt's priority may be left out of some policies."""
        if self.name != "chrt":
            return LEADING_OPERANDS.get(self.name, 0)
        if any(self.dynamic[self.index : self.index + 1]):
            raise UnsupportedSyntax("a chrt priority known only at run time requires explicit review", "wrapper")
        return int(self.index < len(self.arguments) and PRIORITY.fullmatch(self.arguments[self.index]) is not None)

    def run(self) -> Self:
        while self.index < len(self.arguments) and self.take_option():
            pass
        self.take_trailing_script()
        return self

    def take_option(self) -> bool:
        """Consume the option at the current index; False at the first operand or after `--`."""
        token = self.arguments[self.index]
        if token == "--":
            self.index += 1
            return False
        if self.name == "command" and token in COMMAND_LOOKUP:
            self.index = len(self.arguments)
            return False
        if token in self.valued:
            self.record(token, self.value_at(self.index + 1))
            self.index += 2
        elif token in self.flags or (self.name in ASSIGNING_WRAPPERS and ASSIGNMENT.match(token)):
            self.record(token, None)
            self.index += 1
        elif token.startswith("-"):
            self.index += self.take_attached()
        else:
            return False
        return True

    def take_attached(self) -> int:
        """Record an option written with its value attached or bundled with other short flags; return the tokens it spans."""
        token = self.arguments[self.index]
        if token.startswith("--"):
            key, _, value = token.partition("=")
            if not value or key not in self.valued:
                self.refuse(token)
            self.record(key, value)
            return 1
        if self.name == "nice" and token[1:].isdigit():
            return 1
        if token == "-":
            self.refuse(token)
        for position, letter in enumerate(token[1:], 1):
            option = f"-{letter}"
            if option in OPTIONAL_ATTACHED.get(self.name, ()):
                self.record(option, token[position + 1 :] or None)
                return 1
            if option in self.valued:
                return self.take_value(option, token[position + 1 :])
            if option not in self.flags:
                self.refuse(token)
            self.record(option, None)
        return 1

    def take_value(self, option: str, attached: str) -> int:
        if attached or self.index + 1 >= len(self.arguments):
            self.record(option, attached or None)
            return 1
        self.record(option, self.arguments[self.index + 1])
        return 2

    def record(self, option: str, value: str | None) -> None:
        """Note an option and its value; every script option counts, since which one runs is the program's choice."""
        self.seen[option] = value
        if option in SCRIPT_OPTIONS.get(self.name, ()):
            self.scripts.append(value)

    def take_trailing_script(self) -> None:
        """Read options written after the leading operand: `flock <file> -c <script>`, `script <file> -c <script>`.

        Reading stops at the first word that is no option, where a BSD script's own command begins,
        whose arguments are not script options. The scan position is left where it was.
        """
        if self.name not in {"flock", "script"}:
            return
        resume = self.index
        self.index += LEADING_OPERANDS[self.name]
        while self.index < len(self.arguments) and self.arguments[self.index].startswith("-") and self.take_option():
            pass
        self.index = resume

    def value_at(self, position: int) -> str | None:
        return self.arguments[position] if position < len(self.arguments) else None

    def refuse(self, token: str) -> None:
        raise UnsupportedSyntax(f"{self.name} option requires explicit review: {token}", "wrapper")


def script_index(arguments: tuple[str, ...], option: int) -> int:
    """Where the script of a shell's -c sits: the first word after it that is not an option, past a `--`."""
    index = option + 1
    while index < len(arguments) and arguments[index] != "--" and arguments[index][:1] in "-+":
        if arguments[index] in SHELL_VALUED_OPTIONS:
            raise UnsupportedSyntax("a shell option before the -c script requires explicit review", "wrapper")
        index += 1
    index += index < len(arguments) and arguments[index] == "--"
    if index >= len(arguments):
        raise UnsupportedSyntax("shell wrapper has no literal command", "wrapper")
    return index
