"""The shape of the command line a gh call runs in, which decides how far the guard can trust its words."""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import command_policy
import read_only_commands
import shell_inspection
import shell_syntax

PROGRAM = "gh"
# zsh evaluates a subscript, and a value assigned to an integer variable, as arithmetic that may run a
# command substitution the parse never sees: `$name[...]` outside single quotes, or an assignment whose
# value, quoted in any way, holds `[...$(`.
SUBSCRIPT = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\[")
ARITHMETIC_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*\[[^\]]*\$\(")
SHELL_BUILTINS = frozenset({"echo", "false", "printf", "pwd", "true"})
DEVICE_NULL = "/dev/null"
# Beside a heredoc or a substitution only these filters, writing nothing, keep the working directory's remotes
# trusted; such a line stays as #200 left it until #181.
PIPE_FILTERS = frozenset({"cat", "column", "cut", "echo", "grep", "head", "jq", "printf", "tail", "tr", "true", "wc"})
# A heredoc or herestring.
HEREDOC = re.compile(r"<<")
# A redirection target whose path is known only at run time, or that a shell may expand.
RUN_TIME_PATH = re.compile(r"[$`*?\[]")
# Programs that set shell variables, or run code that may: on a line holding one, a variable gh reads,
# such as GH_REPO, GH_HOST, GH_TOKEN, HTTPS_PROXY, SSL_CERT_FILE, or HOME, may differ from the
# harness environment the guard judged. The hook's own environment is the harness's.
ASSIGNING_PROGRAMS = frozenset(
    {"declare", "eval", "export", "getopts", "let", "local", "mapfile", "read", "readarray", "readonly"}
    | {"alias", "hash", "set", "source", ".", "trap", "typeset", "unalias", "unset", "vared", "zparseopts"}
    # builtin, and zsh's precommand modifiers, run any of these by name, so the syntax no longer shows which.
    | {"builtin", "noglob", "nocorrect", "-"}
    # fc, zsh's r, and history rerun or add commands the line's syntax does not show.
    | {"fc", "r", "history"}
    # enable, disable, zmodload, and autoload load, swap, or define builtins and functions, gh's name included.
    | {"enable", "disable", "zmodload", "autoload"}
    # zsh's emulate -c and sched run code given as an argument.
    | {"emulate", "sched"}
)
# Syntax that assigns: a declaration, a loop variable, arithmetic, a ${name:=value} default, or a function,
# which can stand in for a command of the same name.
ASSIGNING_NODES = frozenset({"DeclClause", "ForClause", "CStyleLoop", "ArithmCmd", "ArithmExp", "FuncDecl"})
DEFAULT_ASSIGNMENT = re.compile(r"\$\{[^}]*?:?=")
QUOTED_HEREDOC = re.compile(r"""^<<-?\s*(?:'[^']+'|"[^"]+"|\\\w+)$""")
QUOTED_TEXT = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
INPUT_OPERATOR = re.compile(r"[0-9]*<(?:<<|<-?|>|&)?(?!\()")
INPUT_REDIRECT = re.compile(r"""(?:^|\s)(0?<(?:<<|<-?|>|&)?\s*(?:'[^']*'|"[^"]*"|\S+))""")
# A backslash and newline, which bash removes so the heredoc's command line goes on past it.
LINE_CONTINUATION = re.compile(r"\\\n")
# A substitution holding only an input redirection, such as `$(< .env)`, reads that file in bash.
REDIRECT_SUBSTITUTION = re.compile(r"\$\(\s*<|`\s*<")
# Programs a body substitution may run without changing anything gh reads: the directory, remotes, or files.
PRINTING_PROGRAMS = frozenset({"cat", "echo", "printf"})


@dataclass(frozen=True, slots=True)
class CommandLine:
    """The whole command a gh call runs in, which decides how far its words and directory can be trusted.

    `single_call` says the line is one call with no assignment or wrapper, so every variable comes
    from the harness environment and nothing changes the directory, remotes, or files before gh runs.
    `hides_code` says zsh may run a command substitution inside a subscript or arithmetic assignment,
    and `changes_environment` that the line assigns a variable, before a call or anywhere else, runs a
    program through env with a changed environment, or runs any command behind a wrapper or inside a
    script another program reads, whose assignments the line's own syntax does not show; gh may then
    not see the harness environment.
    `changes_directory` says another command on the line may write a file or run a program, so the
    directory or its remotes may differ from what the hook reads; otherwise gh runs in one of
    `directories`, the hook's own and each a literal cd may enter. `plants_nothing` says nothing on
    the line but one gh call writes a file, and that gh writes into no PATH entry, and `reads_git` that
    a git read on the line may run a program git's configuration names. `arguments` joins every
    command's arguments as the shell passes them, substituted commands included, for the secret scan.
    """

    source: str
    single_call: bool
    hides_code: bool
    changes_environment: bool
    changes_directory: bool = False
    arguments: str = ""
    directories: tuple[Path, ...] = ()
    plants_nothing: bool = False
    reads_git: bool = False


def command_line(source: str, commands: tuple[shell_syntax.Command, ...]) -> CommandLine:
    """Read the line's shape once; it parses the source again, so build it only for a line holding gh."""
    outside = shell_inspection.text_outside_single_quotes(source)
    hides_code = bool(SUBSCRIPT.search(outside) or ARITHMETIC_ASSIGNMENT.search(source))
    changes = (
        _assigns_in_syntax(source)
        or any(_changes_environment(item) for item in commands)
        or any(item.wrapper_depth for item in commands)
    )
    others = [item for item in commands if not is_gh(command_policy.canonical(item))]
    plain = not _builds_text(source)
    filters_only = all(item.arguments[0] in PIPE_FILTERS for item in others)
    directories = _directories(others) if plain or filters_only else None
    reads_only = directories is not None and all(_writes_nothing(item) for item in others if item.arguments[0] != "cd")
    kept = {DEVICE_NULL} if plain else set()
    moves = not reads_only or any(target not in kept for item in others for target in item.writes)
    one_gh = len(commands) - len(others) == 1
    # Another command may write only to /dev/null: any other file may be configuration a later git read runs,
    # such as .git/config or .gitattributes. gh's own output lands only after every earlier command ran.
    writes = [target for item in commands if item not in others for target in item.writes]
    plants = not (plain and not moves and one_gh) or any(_may_plant(target, directories or ()) for target in writes)
    return CommandLine(
        source,
        _is_single_call(source, commands),
        hides_code,
        changes,
        moves,
        " ".join(argument for item in commands for argument in item.arguments),
        directories or (),
        not plants,
        any(item.arguments[0] == "git" for item in others),
    )


def _builds_text(source: str) -> bool:
    """Whether the line holds a heredoc, herestring, or command, process, or arithmetic substitution."""
    if HEREDOC.search(shell_inspection.text_outside_single_quotes(source)):
        return True
    tree = shell_syntax.syntax_tree(source)
    return any(node.get("Type") in {"CmdSubst", "ProcSubst", "ArithmExp"} for node in shell_syntax.nodes(tree))


def _writes_nothing(command: shell_syntax.Command) -> bool:
    """Whether a command only reads and prints, writing no file and running no other program.

    Its words show that, and it is a builtin, or a program PATH finds where no one on this account could plant a
    stand-in. Where its redirections write, the caller judges.
    """
    name = command.arguments[0]
    if command.wrapper_depth or has_inherited_function(name):
        return False
    if not read_only_commands.writes_nothing(command.arguments, command.dynamic):
        return False
    return name in SHELL_BUILTINS or is_system_program(name)


def _directories(others: list[shell_syntax.Command]) -> tuple[Path, ...] | None:
    """Every directory gh may run in: the hook's, and each one a literal cd may enter from any before it.

    A cd that fails, or runs in a subshell, leaves gh in a directory already listed. None when a change of
    directory cannot be followed, or when PATH holds a relative entry that a cd would point elsewhere.
    """
    found = [Path.cwd()]
    for item in others:
        if Path(item.arguments[0]).name not in shell_syntax.DIRECTORY_CHANGES:
            continue
        if item.arguments[0] != "cd" or has_relative_path_entry() or has_inherited_function("cd"):
            return None
        entered = [path for path in _entered(found, item) if path.is_dir()]
        if not entered:
            return None
        found += [path.resolve() for path in entered if path.resolve() not in found]
    return tuple(found)


def _entered(found: list[Path], item: shell_syntax.Command) -> list[Path]:
    """Where a cd may lead from each directory found so far; CDPATH may send a relative one elsewhere."""
    targets = [shell_syntax.changed_directory(directory, item) for directory in found]
    if None in targets:
        return []
    relative = any(not Path(argument).is_absolute() for argument in item.arguments[1:] if argument != "--")
    return [] if relative and os.environ.get("CDPATH") else [path for path in targets if path is not None]


def _may_plant(target: str, directories: tuple[Path, ...]) -> bool:
    """Whether a redirection may write into a PATH entry, from any directory the line may run in."""
    if target == DEVICE_NULL:
        return False
    if RUN_TIME_PATH.search(target) or has_relative_path_entry() or not directories:
        return True
    entries = {Path(entry).resolve() for entry in os.environ.get("PATH", "").split(os.pathsep)}
    paths = [directory / Path(target).expanduser() for directory in directories]
    return any(path.parent.resolve() in entries or path.resolve().parent in entries for path in paths)


def _assigns_in_syntax(source: str) -> bool:
    """Whether the line's syntax assigns a variable: a prefix assignment, declaration, loop, or arithmetic."""
    if DEFAULT_ASSIGNMENT.search(source):
        return True
    return any(
        node.get("Type") in ASSIGNING_NODES or (node.get("Type") == "CallExpr" and node.get("Assigns"))
        for node in shell_syntax.nodes(shell_syntax.syntax_tree(source))
    )


def _changes_environment(command: shell_syntax.Command) -> bool:
    """Whether a command sets variables, or runs another through env with assignments or options."""
    name, *arguments = command.arguments
    name = Path(name).name
    # An inherited function may assign anything, under any name.
    if name in ASSIGNING_PROGRAMS or has_inherited_function(command.arguments[0]):
        return True
    if name in {"print", "printf"} and any(re.match(r"-[A-Za-z]*v", argument) for argument in arguments):
        return True
    return name == "env" and bool(arguments) and ("=" in arguments[0] or arguments[0].startswith("-"))


def _is_single_call(source: str, commands: tuple[shell_syntax.Command, ...]) -> bool:
    """One statement holding one call; any other command only prints text into its words."""
    head, *substituted = commands
    if head.wrapper_depth or REDIRECT_SUBSTITUTION.search(source):
        return False
    if not all(_only_prints(item) for item in substituted):
        return False
    statements = shell_syntax.syntax_tree(source).get("Stmts", [])
    if len(statements) != 1:
        return False
    statement = statements[0]
    command = statement.get("Cmd") or {}
    flags = ("Background", "Coprocess", "Negated", "Disown")
    return (
        not any(statement.get(flag) for flag in flags)
        and command.get("Type") == "CallExpr"
        and not command.get("Assigns")
    )


def _only_prints(command: shell_syntax.Command) -> bool:
    """Whether a command inside a substitution prints only literal text or its heredoc, never a file."""
    name = command.arguments[0]
    if name not in PRINTING_PROGRAMS or command.wrapper_depth or command.writes or command.has_dynamic_words:
        return False
    if has_inherited_function(name):
        return False
    if any(not QUOTED_HEREDOC.match(redirect) for redirect in input_redirects(command)):
        return False
    if name != "cat":
        # printf repeats and joins its format, and printf and echo -e turn escapes such as \147 into text
        # the scan of the source never sees; only a lone literal format or escape-free echo prints as written.
        if any("\\" in argument or argument == "-e" for argument in command.arguments):
            return False
        return name != "printf" or (len(command.arguments) == 2 and "%" not in command.arguments[1])
    redirects = input_redirects(command)
    heredoc_only = len(command.arguments) == 1 and len(redirects) == 1 and bool(QUOTED_HEREDOC.match(redirects[0]))
    return heredoc_only and is_system_program(name)


def is_system_program(name: str) -> bool:
    """Whether PATH finds the program outside the working tree in a place the user cannot write.

    echo and printf are shell builtins and never looked up; cat is, so a planted ./cat on PATH must not pass.
    """
    found = shutil.which(name)
    if found is None or not Path(found).is_absolute():
        return False
    resolved = Path(found).resolve()
    # Both the path PATH names and the file it resolves to, with every directory above each, must be locked,
    # so no symlink hop or parent directory lets this account swap the program.
    chain = (Path(found), *Path(found).parents, resolved, *resolved.parents)
    writable = any(os.access(path, os.W_OK) for path in chain)
    return not writable and not resolved.is_relative_to(Path.cwd().resolve())


def is_gh(command: shell_syntax.Command) -> bool:
    """Whether the canonical command runs gh."""
    return not command.program_is_dynamic and command.arguments[0] == PROGRAM


def input_redirects(command: shell_syntax.Command) -> list[str]:
    """Each input redirection in a call's trailer, as written.

    Any extra operator counts, even one joined to a quoted heredoc delimiter or continued onto the
    next line after it, so a later redirection cannot hide behind the first.
    """
    first_line = LINE_CONTINUATION.sub("", command.trailer).split("\n", 1)[0]
    found = [match[1] for match in INPUT_REDIRECT.finditer(first_line)]
    operators = INPUT_OPERATOR.findall(QUOTED_TEXT.sub("Q", first_line))
    return found if len(operators) == len(found) else [*found, *operators[len(found) :]]


def has_inherited_function(name: str) -> bool:
    """Whether the environment exports a bash function of this name, which bash runs before a builtin or program."""
    return any(key.startswith(f"BASH_FUNC_{name}%%") or key == f"BASH_FUNC_{name}()" for key in os.environ)


def has_relative_path_entry() -> bool:
    """Whether PATH holds an empty or relative entry, which names another directory after a cd."""
    return any(not entry or not Path(entry).is_absolute() for entry in os.environ.get("PATH", "").split(os.pathsep))


def has_writable_path_entry_before(name: str) -> bool:
    """Whether a PATH entry searched before the program is relative, empty, or where the agent can write.

    Another command on the same line could place a stand-in there before the program runs.
    """
    found = shutil.which(name)
    found_directory = Path(found).absolute().parent if found else None
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or not Path(entry).is_absolute():
            return True
        if in_agent_roots(Path(entry).absolute()) or in_agent_roots(Path(entry).resolve()):
            return True
        if Path(entry).absolute() == found_directory:
            return False
    return False


def in_agent_roots(path: Path) -> bool:
    """Whether a path lies in the working tree or a temporary directory, where a sandboxed agent writes."""
    roots = [Path.cwd().resolve(), Path("/tmp").resolve(), Path("/private/tmp")]
    roots += [Path(os.environ["TMPDIR"]).resolve()] if os.environ.get("TMPDIR") else []
    return any(path.is_relative_to(root) for root in roots)
