"""Inspect a conservative shell subset using shfmt's parser, never by executing input."""

from dataclasses import dataclass, replace
from collections.abc import Iterator
import json
from pathlib import Path
import re
import subprocess
from typing import Self

from shell_words import UnsupportedSyntax, literal_word, source_text, spreads


COMMAND_PREVIEW_LIMIT = 200
RUN_TIME_PLACEHOLDER = "_"
# Statements, words, arithmetic, loops and branches, and tests that the inspection understands.
ALLOWED_NODES = frozenset(
    {
        None,
        *(
            "File CallExpr BinaryCmd Subshell Block TimeClause DeclClause "
            "Word Lit SglQuoted DblQuoted ParamExp CmdSubst ProcSubst "
            "ArithmExp ArithmCmd BinaryArithm UnaryArithm ParenArithm "
            "ForClause WordIter CStyleLoop WhileClause IfClause CaseClause CaseItem "
            "TestClause BinaryTest UnaryTest ParenTest"
        ).split(),
    }
)
DIRECTORY_CHANGES = frozenset({"cd", "pushd", "popd"})
SHELLS = frozenset({"bash", "dash", "ksh", "sh", "zsh"})
COMMAND_LOOKUP = frozenset({"-v", "-V"})
# Options of echo, which writes its remaining arguments; the backslash escapes they toggle are refused.
ECHO_OPTIONS = re.compile(r"-[neE]+")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# Process wrappers run their trailing arguments as a command. Each entry lists the flags without an
# operand and the options whose operand is the next token; unknown options are refused, not skipped.
WRAPPERS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "caffeinate": (frozenset({"-d", "-i", "-m", "-s", "-u"}), frozenset({"-t", "-w"})),
    "command": (frozenset({"-p"}), frozenset()),
    "env": (frozenset({"-i", "--ignore-environment", "-0", "--null"}), frozenset({"-u", "--unset", "-C", "--chdir"})),
    "exec": (frozenset({"-c", "-l"}), frozenset({"-a"})),
    "nice": (frozenset(), frozenset({"-n", "--adjustment"})),
    "nohup": (frozenset(), frozenset()),
    "time": (frozenset({"-p", "-l", "-h", "-a", "--portability"}), frozenset({"-o", "-f", "--output", "--format"})),
    "timeout": (
        frozenset({"--preserve-status", "--foreground", "-v"}),
        frozenset({"-k", "--kill-after", "-s", "--signal"}),
    ),
    "xargs": (
        frozenset({"-0", "-r", "-t", "-p", "-x", "-o", "--null", "--no-run-if-empty", "--verbose", "--interactive"}),
        frozenset(
            {"-n", "-I", "-L", "-P", "-s", "-d", "-E", "-a", "--max-args", "--replace", "--max-lines", "--max-procs"}
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class Command:
    """A parsed literal command and its original source representation.

    `dynamic` flags arguments whose value is only known at run time (a glob or a parameter other
    than the home directory); such arguments carry their source text. `writes` lists the files
    that output redirections would create or overwrite. `appends_input` marks a command that xargs
    runs with further arguments read from its input. `spreading` flags arguments that may become
    several words at run time, options included.
    """

    raw: str
    arguments: tuple[str, ...]
    wrapper_depth: int = 0
    redirections: tuple[str, ...] = ()
    words: tuple[str, ...] = ()
    trailer: str = ""
    dynamic: tuple[bool, ...] = ()
    writes: tuple[str, ...] = ()
    appends_input: bool = False
    spreading: tuple[bool, ...] = ()

    def __post_init__(self) -> None:
        if not self.words:
            object.__setattr__(self, "words", self.arguments)
        if not self.dynamic:
            object.__setattr__(self, "dynamic", (False,) * len(self.arguments))
        if not self.spreading:
            object.__setattr__(self, "spreading", (False,) * len(self.arguments))

    @property
    def words_text(self) -> str:
        """The command's own words, without redirections or heredoc bodies, for rule matching."""
        return " ".join(self.words)

    @property
    def command_words_text(self) -> str:
        """The command's words with each argument containing whitespace as a placeholder.

        Such an argument is prose such as a PR body or commit message; a shell runs it as a command
        only through eval or a shell -c wrapper, whose script parse judges as separate commands.
        """
        return " ".join(
            RUN_TIME_PLACEHOLDER if re.search(r"\s", argument) else word
            for word, argument in zip(self.words, self.arguments, strict=True)
        )

    @property
    def static_words_text(self) -> str:
        """The command's words with each run-time word as a plain placeholder, for judging the static form."""
        return " ".join(
            RUN_TIME_PLACEHOLDER if dynamic else word for word, dynamic in zip(self.words, self.dynamic, strict=True)
        )

    @property
    def hides_options(self) -> bool:
        """Whether an option can reach the program unseen: quoted or escaped, or inside a spreading expansion."""
        quoted_option = any(
            argument.startswith("-") and word != argument
            for word, argument in zip(self.words, self.arguments, strict=True)
        )
        return quoted_option or any(self.spreading)

    @property
    def has_dynamic_words(self) -> bool:
        return any(self.dynamic)

    @property
    def program_is_dynamic(self) -> bool:
        return bool(self.dynamic) and self.dynamic[0]

    def rebased(self, index: int, head: tuple[str, ...] = (), depth: int | None = None) -> Self:
        """Keep the arguments from one index onward, optionally behind a canonical head or one wrapper deeper."""
        words = (*head, *self.words[index:])
        raw = " ".join((*words, self.trailer)).rstrip()
        wrapper_depth = self.wrapper_depth if depth is None else depth
        return replace(
            self,
            raw=raw,
            arguments=(*head, *self.arguments[index:]),
            wrapper_depth=wrapper_depth,
            words=words,
            dynamic=((False,) * len(head)) + self.dynamic[index:],
            spreading=((False,) * len(head)) + self.spreading[index:],
        )


def command_preview(source: str) -> str:
    """Bound guard diagnostics without repeating inline script bodies."""
    lines = source.splitlines()
    first = lines[0] if lines else ""
    preview = first[:COMMAND_PREVIEW_LIMIT]
    if len(first) > COMMAND_PREVIEW_LIMIT or len(lines) > 1:
        return preview + "\nRemaining command text omitted."
    return preview


def parse(source: str, depth: int = 0) -> tuple[Command, ...]:
    """Parse literal commands, including static shell and process wrappers, and reject unknown syntax."""
    if not source.strip():
        return ()
    if depth > 8:
        raise UnsupportedSyntax("shell wrapper nesting exceeds the inspection limit", "wrapper")
    records = tuple(nodes(syntax_tree(source)))
    owners = {id(node["Cmd"]): node for node in records if isinstance(node.get("Cmd"), dict)}
    if any(node.get("Type") not in ALLOWED_NODES for node in records):
        raise UnsupportedSyntax("dynamic or unsupported shell syntax requires explicit review", "expansion")
    data = source.encode()
    feeds = pipe_feeds(records, data)
    commands: list[Command] = []
    for node in records:
        if node.get("Type") != "CallExpr" or not node.get("Args"):
            continue
        owner = owners.get(id(node), node)
        command = replace(literal_command(node, owner, data), wrapper_depth=depth)
        commands.append(command)
        commands.extend(unwrapped(command))
        innermost = commands[-1]
        if script := shell_script(innermost):
            commands.extend(parse(script, innermost.wrapper_depth + 1))
        elif Path(innermost.arguments[0]).name in SHELLS and (
            stdin := input_script(owner, feeds.get(id(owner)), data)
        ):
            commands.extend(parse(stdin, innermost.wrapper_depth + 1))
    return tuple(commands)


def reached_directories(directories: tuple[Path | None, ...], command: Command) -> tuple[Path | None, ...]:
    """Add where a cd, pushd, or popd may lead to the directories reachable so far; None is one known only at run time.

    Earlier directories stay reachable, since a cd inside a subshell or before || may not take effect.
    """
    if Path(command.arguments[0]).name not in DIRECTORY_CHANGES:
        return directories
    return tuple(dict.fromkeys([*directories, *(changed_directory(directory, command) for directory in directories)]))


def changed_directory(directory: Path | None, item: Command) -> Path | None:
    """Follow a cd or pushd to a literal directory; any other change leaves the directory unknown."""
    name, arguments = Path(item.arguments[0]).name, item.arguments
    operands = [index for index, argument in enumerate(arguments[1:], 1) if not argument.startswith("-")]
    if directory is None or name == "popd" or "-" in arguments or (name == "pushd" and not operands):
        return None
    if not operands:
        return Path.home()
    index = operands[0]
    return None if item.dynamic[index] else directory / arguments[index]


def statement_writes(statement: dict, data: bytes) -> tuple[str, ...]:
    redirects = [redirect for redirect in statement.get("Redirs", []) if redirect.get("Word")]
    targets = [literal_word(redirect["Word"], data)[0] for redirect in redirects]
    return tuple(
        target for redirect, target in zip(redirects, targets, strict=True) if writes_file(redirect, target, data)
    )


def is_one_simple_command(source: str) -> bool:
    """Whether the source is one plain call: no list, pipe, background, negation, compound, assignment, or redirect."""
    statements = syntax_tree(source).get("Stmts", [])
    if len(statements) != 1:
        return False
    statement = statements[0]
    flags = ("Background", "Coprocess", "Negated", "Disown", "Redirs")
    command = statement.get("Cmd")
    return (
        not any(statement.get(flag) for flag in flags)
        and isinstance(command, dict)
        and command.get("Type") == "CallExpr"
        and not command.get("Assigns")
    )


def pipe_feeds(records: tuple[dict, ...], data: bytes) -> dict[int, dict]:
    """Map each statement on the reading side of a pipe to the statement whose output it reads.

    Records list an outer pipeline before the pipelines inside it, so the nearest pipe wins.
    """
    pipes = (node for node in records if node.get("Type") == "BinaryCmd" and is_pipe(node, data))
    return {id(statement): pipe["X"] for pipe in pipes for statement in nodes(pipe["Y"]) if "Cmd" in statement}


def is_pipe(node: dict, data: bytes) -> bool:
    """Whether a binary command is a pipe (| or |&), judged by its operator text, not by parser codes."""
    offset = node["OpPos"]["Offset"]
    return data[offset : offset + 1] == b"|" and data[offset + 1 : offset + 2] != b"|"


def input_script(owner: dict, feed: dict | None, data: bytes) -> str:
    """Return the static script a shell reads from its input; a redirection replaces a pipe.

    A `<(...)` argument hands the shell a script known only at run time, and of several input
    redirections only one reaches the shell, so both are refused rather than guessed.
    """
    inputs = [redirect for redirect in owner.get("Redirs", []) if redirect_operator(redirect, data) in {"<", "<<<"}]
    if reads_process_substitution(owner.get("Cmd", owner), data) or len(inputs) > 1:
        raise computed_input()
    if script := heredoc_script(owner) + here_string_script(owner, data) + file_script(owner, data):
        return script
    return piped_script(feed, data) if feed else ""


def reads_process_substitution(node: dict, data: bytes) -> bool:
    parts = (part for word in node["Args"] for part in word.get("Parts", []))
    return any(part.get("Type") == "ProcSubst" and source_text(part, data).startswith("<(") for part in parts)


def here_string_script(owner: dict, data: bytes) -> str:
    words = [
        redirect["Word"]
        for redirect in owner.get("Redirs", [])
        if redirect.get("Word") and redirect_operator(redirect, data) == "<<<"
    ]
    return "".join(static_script(word, data) + "\n" for word in words)


def file_script(owner: dict, data: bytes) -> str:
    """Return the scripts a shell reads from redirected files, read now; refuse any that is not a readable file.

    Only a regular file is read, so a FIFO or device cannot stall the hook.
    """
    words = [
        redirect["Word"]
        for redirect in owner.get("Redirs", [])
        if redirect.get("Word") and not redirect.get("Hdoc") and redirect_operator(redirect, data) == "<"
    ]
    return "".join(read_script(Path(static_script(word, data))) for word in words)


def read_script(path: Path) -> str:
    try:
        if not path.is_file():
            raise computed_input()
        return path.read_text()
    except (OSError, UnicodeDecodeError) as error:
        raise computed_input() from error


def piped_script(statement: dict, data: bytes) -> str:
    """Return the text a literal echo or plain printf writes into the pipe, refusing any other source."""
    command = statement.get("Cmd") or {}
    if command.get("Type") != "CallExpr" or not command.get("Args"):
        raise computed_input()
    program, *arguments = (static_script(word, data) for word in command["Args"])
    name = Path(program).name
    if name == "echo":
        while arguments and ECHO_OPTIONS.fullmatch(arguments[0]):
            arguments.pop(0)
        text = " ".join(arguments)
    elif name == "printf" and len(arguments) == 1 and "%" not in arguments[0]:
        text = arguments[0]
    else:
        raise computed_input()
    # echo and printf may turn a backslash escape into a line break, which separates commands.
    if "\\" in text:
        raise computed_input()
    return text


def static_script(word: dict, data: bytes) -> str:
    value, dynamic = literal_word(word, data)
    if dynamic:
        raise computed_input()
    return value


def computed_input() -> UnsupportedSyntax:
    return UnsupportedSyntax("a shell reading a computed script from its input requires explicit review", "wrapper")


def heredoc_script(owner: dict) -> str:
    """Return the static script a shell reads from a heredoc, refusing one the shell computes."""
    bodies = [redirect["Hdoc"] for redirect in owner.get("Redirs", []) if redirect.get("Hdoc")]
    if not bodies:
        return ""
    parts = [part for body in bodies for part in body.get("Parts", [])]
    if any(part.get("Type") != "Lit" for part in parts):
        raise UnsupportedSyntax("a shell heredoc whose text is computed requires explicit review", "heredoc")
    return "".join(part.get("Value", "") for part in parts)


def syntax_tree(source: str) -> dict:
    """Obtain shfmt's syntax tree, refusing to guess about input it cannot parse."""
    try:
        result = subprocess.run(
            ["shfmt", "-ln", "bash", "--to-json"], input=source, text=True, capture_output=True, timeout=5, check=False
        )
        if result.returncode:
            raise UnsupportedSyntax("unsupported or invalid shell syntax", "parse-failure")
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise UnsupportedSyntax("shell parser unavailable; command cannot be validated", "parse-failure") from error


def nodes(value: object) -> Iterator[dict]:
    """Walk parser records without interpreting position metadata as executable code."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def literal_command(node: dict, owner: dict, data: bytes) -> Command:
    """Decode one call expression together with the statement text that owns it."""
    raw = source_text(owner, data).strip()
    if owner.get("Semicolon") and raw.endswith(";"):
        raw = raw[:-1].rstrip()
    if owner.get("Background") and raw.endswith("&"):
        raw = raw[:-1].rstrip()
    redirects = [redirect for redirect in owner.get("Redirs", []) if redirect.get("Word")]
    decoded = [literal_word(word, data) for word in node["Args"]]
    targets = [literal_word(redirect["Word"], data)[0] for redirect in redirects]
    return Command(
        raw,
        tuple(value for value, _ in decoded),
        redirections=tuple(targets),
        words=tuple(source_text(word, data) for word in node["Args"]),
        trailer=" ".join(source_text(redirect, data) for redirect in redirects),
        dynamic=tuple(flag for _, flag in decoded),
        spreading=tuple(spreads(word, data) for word in node["Args"]),
        writes=statement_writes(owner, data),
    )


def writes_file(redirect: dict, target: str, data: bytes) -> bool:
    """Whether a redirection creates or overwrites a file, judged by its operator text, not by parser codes."""
    symbol = redirect_operator(redirect, data)
    if not symbol:
        return True
    if symbol in {">&", "<&"}:
        return symbol == ">&" and not (target.isdigit() or target == "-")
    return symbol in {">", ">>", ">|", "&>", "&>>", "<>"}


def redirect_operator(redirect: dict, data: bytes) -> str:
    operator = re.match(r"\d*(&>>|&>|>>|>\||>&|<&|<<<|<>|<|>)", source_text(redirect, data))
    return operator.group(1) if operator else ""


def unwrapped(command: Command) -> list[Command]:
    """Peel process wrappers so policy sees the program they eventually run."""
    exposed: list[Command] = []
    while (index := wrapped_index(command.arguments)) is not None:
        appends_input = command.appends_input or Path(command.arguments[0]).name == "xargs"
        command = replace(command.rebased(index, depth=command.wrapper_depth + 1), appends_input=appends_input)
        exposed.append(command)
    return exposed


def wrapped_index(arguments: tuple[str, ...]) -> int | None:
    """Locate the command a process wrapper runs, or None when the call is not a wrapper invocation."""
    name = Path(arguments[0]).name
    if name not in WRAPPERS:
        return None
    _, valued = WRAPPERS[name]
    index = 1
    while index < len(arguments):
        token = arguments[index]
        if token == "--":
            index += 1
            break
        if name == "command" and token in COMMAND_LOOKUP:
            return None
        if token in valued:
            index += 2
        elif (name == "env" and ASSIGNMENT.match(token)) or is_flag(name, token):
            index += 1
        elif token.startswith("-"):
            raise UnsupportedSyntax(f"{name} option requires explicit review: {token}", "wrapper")
        else:
            break
    if name == "timeout":
        index += 1
    return index if index < len(arguments) else None


def is_flag(name: str, token: str) -> bool:
    """Recognize a wrapper's options that carry no separate operand, including attached-value short forms."""
    flags, valued = WRAPPERS[name]
    if token in flags:
        return True
    if token.startswith("--"):
        key, _, value = token.partition("=")
        return bool(value) and key in valued
    if len(token) > 2 and token[:2] in valued:
        return True
    if name == "nice":
        return token[1:].isdigit()
    return name == "caffeinate" and re.fullmatch(r"-[dimsu]+", token) is not None


def shell_script(command: Command) -> str:
    """Return the literal script that eval or a shell -c invocation runs, or an empty string."""
    arguments = command.arguments
    executable = Path(arguments[0]).name
    if executable == "eval":
        if any(command.dynamic[1:]):
            raise UnsupportedSyntax("eval of a computed script requires explicit review", "wrapper")
        return " ".join(arguments[1:])
    if executable not in SHELLS:
        return ""
    option = next(
        (
            index
            for index, argument in enumerate(arguments[1:], 1)
            if argument.startswith("-") and not argument.startswith("--") and "c" in argument
        ),
        None,
    )
    if option is None:
        return ""
    if option + 1 >= len(arguments):
        raise UnsupportedSyntax("shell wrapper has no literal command", "wrapper")
    if command.dynamic[option + 1]:
        raise UnsupportedSyntax("a shell wrapper running a computed script requires explicit review", "wrapper")
    return arguments[option + 1]
