"""Inspect a conservative shell subset using shfmt's parser, never by executing input."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
import subprocess
from typing import Self

import shell_input
from shell_words import UnsupportedSyntax, literal_word, nodes, source_text, spreads
from shell_wrappers import ASSIGNMENT, WRAPPERS, OptionScan, wrapped_index


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
SHELLS = frozenset(
    {
        "ash",
        "bash",
        "dash",
        "hush",
        "ksh",
        "mksh",
        "oksh",
        "pdksh",
        "posh",
        "rbash",
        "sh",
        "yash",
        "zsh",
    }
)
# Shells whose syntax is not bash's, and names ending in sh that are no known shell: parsing their -c
# script as bash would misread it, so a -c (or --command) option asks instead.
FOREIGN_SHELLS = frozenset({"csh", "elvish", "es", "fish", "nu", "rc", "tcsh"})
SHELL_LOOKALIKE = re.compile(r"[a-z0-9_.-]*sh")


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
    def command_arguments_text(self) -> str:
        """The command's decoded arguments, quotes removed, with each argument containing whitespace as a placeholder."""
        return " ".join(
            RUN_TIME_PLACEHOLDER if re.search(r"\s", argument) else argument for argument in self.arguments
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


def parse(source: str, depth: int = 0, directories: tuple[Path | None, ...] = ()) -> tuple[Command, ...]:
    """Parse literal commands, including static shell and process wrappers, and reject unknown syntax.

    `directories` are where the source may start running, the working directory by default; a
    script file a shell reads is looked up in each directory the source may have reached.
    """
    directories = directories or (Path.cwd(),)
    if not source.strip():
        return ()
    if depth > 8:
        raise UnsupportedSyntax("shell wrapper nesting exceeds the inspection limit", "wrapper")
    records = tuple(nodes(syntax_tree(source)))
    owners = {id(node["Cmd"]): node for node in records if isinstance(node.get("Cmd"), dict)}
    if any(node.get("Type") not in ALLOWED_NODES for node in records):
        raise UnsupportedSyntax("dynamic or unsupported shell syntax requires explicit review", "expansion")
    timed = {id(node["Stmt"].get("Cmd")) for node in records if node.get("Type") == "TimeClause" and node.get("Stmt")}
    data = source.encode()
    sources = shell_input.InputSources.of(records, data)
    commands: list[Command] = []
    for node in records:
        if node.get("Type") != "CallExpr" or not node.get("Args"):
            continue
        owner = owners.get(id(node), node)
        hidden = id(node) in timed or bool(owner.get("Negated"))
        command = replace(literal_command(node, owner, data), wrapper_depth=depth + hidden)
        layers = [command, *unwrapped(command)]
        commands += layers
        for layer in layers:
            directories = reached_directories(directories, layer)
        innermost = layers[-1]
        if script := shell_script(innermost):
            scripts = [script]
        elif Path(innermost.arguments[0]).name in SHELLS:
            scripts = sources.scripts(owner, directories)
        else:
            scripts = []
        commands += [
            nested for script in scripts for nested in parse(script, innermost.wrapper_depth + 1, directories)
        ]
    return tuple(commands)


def reached_directories(directories: tuple[Path | None, ...], command: Command) -> tuple[Path | None, ...]:
    """Add where a cd, pushd, popd, or env -C may lead to the directories reachable so far; None is one known only at run time.

    Earlier directories stay reachable, since a cd inside a subshell or before || may not take effect.
    """
    name = Path(command.arguments[0]).name
    if name == "env" and (target := env_directory(command)) != "":
        reached = [None if target is None or directory is None else directory / target for directory in directories]
    elif name in DIRECTORY_CHANGES:
        reached = [changed_directory(directory, command) for directory in directories]
    else:
        return directories
    return tuple(dict.fromkeys([*directories, *reached]))


def env_directory(command: Command) -> str | None:
    """The directory the last env -C or --chdir names: "" without the option, None when known only at run time."""
    arguments, index, target = command.arguments, 1, ""
    while index < len(arguments) and (arguments[index].startswith("-") or ASSIGNMENT.match(arguments[index])):
        argument = arguments[index]
        if argument in {"-C", "--chdir"} and index + 1 < len(arguments):
            target = None if command.dynamic[index + 1] else arguments[index + 1]
        elif argument.startswith(("--chdir=", "-C")):
            target = None if command.dynamic[index] else argument.split("=", 1)[-1].removeprefix("-C")
        index += 2 if argument in {"-u", "--unset", "-C", "--chdir"} else 1
    return target


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


def shell_script(command: Command) -> str:
    """Return the literal script that eval, a shell -c invocation, or a script-running wrapper runs, or an empty string."""
    arguments = command.arguments
    executable = Path(arguments[0]).name
    if executable == "eval":
        if any(command.dynamic[1:]):
            raise UnsupportedSyntax("eval of a computed script requires explicit review", "wrapper")
        return " ".join(arguments[1:])
    if executable in WRAPPERS:
        return wrapper_script(command, executable)
    foreign = executable in FOREIGN_SHELLS or (executable not in SHELLS and SHELL_LOOKALIKE.fullmatch(executable))
    if executable not in SHELLS and not foreign:
        return ""
    option = next(
        (
            index
            for index, argument in enumerate(arguments[1:], 1)
            if argument.startswith("-") and (foreign or not argument.startswith("--")) and "c" in argument
        ),
        None,
    )
    if option is None:
        return ""
    if foreign:
        raise UnsupportedSyntax(
            f"{executable} may run its -c argument as a script this inspection cannot parse; requires explicit review",
            "wrapper",
        )
    if option + 1 >= len(arguments):
        raise UnsupportedSyntax("shell wrapper has no literal command", "wrapper")
    if command.dynamic[option + 1]:
        raise UnsupportedSyntax("a shell wrapper running a computed script requires explicit review", "wrapper")
    return arguments[option + 1]


def wrapper_script(command: Command, name: str) -> str:
    """The script a wrapper such as script -c, flock -c, or watch hands to a shell, or an empty string."""
    arguments = command.arguments
    scan = OptionScan(name, arguments).run()
    if not scan.runs_script:
        return ""
    if any(command.dynamic):
        raise UnsupportedSyntax(f"a {name} command string built at run time requires explicit review", "wrapper")
    if name == "watch":
        return " ".join(arguments[scan.index :])
    if scan.script is None:
        raise UnsupportedSyntax(f"{name} has no literal command", "wrapper")
    return scan.script
