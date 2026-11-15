"""The shape of the command line a gh call runs in, which decides how far the guard can trust its words."""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import command_policy
import shell_inspection
import shell_syntax

PROGRAM = "gh"
# zsh evaluates a subscript, and a value assigned to an integer variable, as arithmetic that may run a
# command substitution the parse never sees: `$name[...]` outside single quotes, or an assignment whose
# value, quoted in any way, holds `[...$(`.
SUBSCRIPT = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\[")
ARITHMETIC_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*\[[^\]]*\$\(")
SHELL_BUILTINS = frozenset({"echo", "printf", "true"})
# Programs that only print or filter output and cannot write a file; beside them nothing on the line can change
# the directory or remotes. sort -o and uniq's output argument write files, so neither is here.
OUTPUT_FILTERS = frozenset(
    {"cat", "column", "cut", "echo", "grep", "head", "jq", "printf", "tail", "tr", "true", "wc"}
)
# Programs that set shell variables, or run code that may: on a line holding one, a variable gh reads,
# such as GH_REPO, GH_HOST, GH_TOKEN, HTTPS_PROXY, SSL_CERT_FILE, or HOME, may differ from the
# harness environment the guard judged. The hook's own environment is the harness's.
ASSIGNING_PROGRAMS = frozenset(
    {"declare", "eval", "export", "getopts", "let", "local", "mapfile", "read", "readarray", "readonly"}
    | {"alias", "hash", "set", "source", ".", "trap", "typeset", "unalias", "unset", "vared", "zparseopts"}
)
# Syntax that assigns: a declaration, a loop variable, arithmetic, a ${name:=value} default, or a function,
# which can stand in for a command of the same name.
ASSIGNING_NODES = frozenset({"DeclClause", "ForClause", "CStyleLoop", "ArithmCmd", "ArithmExp", "FuncDecl"})
DEFAULT_ASSIGNMENT = re.compile(r"\$\{[^}]*?:?=")
QUOTED_HEREDOC = re.compile(r"""^<<-?\s*(?:'[^']+'|"[^"]+"|\\\w+)$""")
QUOTED_TEXT = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
INPUT_OPERATOR = re.compile(r"[0-9]*<(?:<<|<-?|>|&)?(?!\()")
INPUT_REDIRECT = re.compile(r"""(?:^|\s)(0?<(?:<<|<-?|>|&)?\s*(?:'[^']*'|"[^"]*"|\S+))""")
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
    `changes_directory` says another command on the line is not an output filter, so the directory or
    its remotes may differ from what the hook reads, and `arguments` joins every command's arguments
    as the shell passes them, substituted commands included, for the secret scan.
    """

    source: str
    single_call: bool
    hides_code: bool
    changes_environment: bool
    changes_directory: bool = False
    arguments: str = ""


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
    moves = not all(_is_output_filter(item) for item in others)
    arguments = " ".join(argument for item in commands for argument in item.arguments)
    return CommandLine(source, _is_single_call(source, commands), hides_code, changes, moves, arguments)


def _is_output_filter(command: shell_syntax.Command) -> bool:
    """Whether a command only prints or filters and writes no file.

    It is a listed builtin, or a listed program PATH finds where no one on this account could plant a stand-in.
    """
    name = command.arguments[0]
    if name not in OUTPUT_FILTERS or command.writes or has_inherited_function(name):
        return False
    return name in SHELL_BUILTINS or is_system_program(name)


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
    if name in ASSIGNING_PROGRAMS:
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

    Any extra operator counts, even one joined to a quoted heredoc delimiter, so a later redirection
    cannot hide behind the first.
    """
    first_line = command.trailer.split("\n", 1)[0]
    found = [match[1] for match in INPUT_REDIRECT.finditer(first_line)]
    operators = INPUT_OPERATOR.findall(QUOTED_TEXT.sub("Q", first_line))
    return found if len(operators) == len(found) else [*found, *operators[len(found) :]]


def has_inherited_function(name: str) -> bool:
    """Whether the environment exports a bash function of this name, which bash runs before a builtin or program."""
    return any(key.startswith(f"BASH_FUNC_{name}%%") or key == f"BASH_FUNC_{name}()" for key in os.environ)
