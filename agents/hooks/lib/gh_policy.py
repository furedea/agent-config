"""Judge each gh call by its effect: classify it, find where it acts, and look the pair up in the gh policy table.

A read, or a change to the local checkout only, runs on any repository. A write runs unprompted
only when a grant covers its operation on the target class; every other write asks, as does any
call the guard cannot classify. What a granted call sends to GitHub is scanned for secrets first.
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import command_policy
import gh_catalog
import gh_invocation
import gh_options
import gh_repository
import hook_decision
import secret_content
import shell_inspection
import shell_syntax
import trusted_owners
from gh_catalog import Catalog, Effect, TargetClass
from gh_invocation import GhCall, Unclassified
from gh_repository import Repository
from hook_decision import Verdict

PROGRAM = "gh"
# zsh evaluates a subscript, and a value assigned to an integer variable, as arithmetic that may run a
# command substitution the parse never sees: `$name[...]` outside single quotes, or an assignment whose
# value, quoted in any way, holds `[...$(`.
SUBSCRIPT = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\[")
ARITHMETIC_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*\[[^\]]*\$\(")
SENT_FILE_LIMIT_BYTES = 100000
REMOTE_LOOKUP_TIMEOUT_SECONDS = 5
GITHUB_HOST = "github.com"
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
# Input redirections in a call's trailer: a heredoc whose delimiter is quoted keeps its body literal
# and in the line; a file is read at run time; anything else, a herestring, an unquoted heredoc, or a
# descriptor copy, may carry text the guard cannot read.
QUOTED_HEREDOC = re.compile(r"""^<<-?\s*(?:'[^']+'|"[^"]+"|\\\w+)$""")
INPUT_FILE = re.compile(r"^<\s*((?:~/)?[^\s$`'\"\\*?\[<>&(~][^\s$`'\"\\*?\[<>&(]*)$")
# A file named by a quoted parameter, which stays one path and is read like a body file named at run time.
RUN_TIME_FILE = re.compile(r'^<\s*"[^"`]*\$[^"`]*"$')
QUOTED_TEXT = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
INPUT_OPERATOR = re.compile(r"[0-9]*<(?:<<|<-?|>|&)?(?!\()")
INPUT_REDIRECT = re.compile(r"""(?:^|\s)(0?<(?:<<|<-?|>|&)?\s*(?:'[^']*'|"[^"]*"|\S+))""")
# A substitution holding only an input redirection, such as `$(< .env)`, reads that file in bash.
REDIRECT_SUBSTITUTION = re.compile(r"\$\(\s*<|`\s*<")
# A run-time path the guard would expand differently from the shell: a glob, substitution, tilde,
# escape, parameter operator or subscript, or a zsh modifier such as `$f:h`.
UNEXPANDABLE_PATH = re.compile(r"[`*?\[~\\]|\$\(|\$\{[^}]*[^A-Za-z0-9_}]|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?:")
# A word's single-quoted, double-quoted, and bare parts, in order.
SHELL_PART = re.compile(r"""'[^']*'|"[^"]*"|[^'"]+""")
# A plain parameter in a run-time path; one the environment lacks expands to nothing, as in the shell.
PLAIN_PARAMETER = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})")
# Programs a body substitution may run without changing anything gh reads: the directory, remotes, or files.
PRINTING_PROGRAMS = frozenset({"cat", "echo", "printf"})
IRREVERSIBLE_REASON = "cannot be taken back or promotes work (class D)"
TARGET_REASONS = {
    TargetClass.UNTRUSTED: "writes to a repository whose owner is not in trusted_owners.json (class C)",
    TargetClass.UNRESOLVED: "writes to a repository the guard cannot determine before the call (class C)",
    TargetClass.NODE: "is a GraphQL mutation outside the reversible allowlist (class D)",
    TargetClass.TRUSTED: "is not granted on a trusted repository",
}


@dataclass(frozen=True, slots=True)
class GhRules:
    """Everything the gh judgement reads: the policy table, the trusted owners, and the secret patterns."""

    catalog: Catalog
    trusted: trusted_owners.TrustedOwners
    secret_patterns: Path


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
    moves = not all(item.arguments[0] in OUTPUT_FILTERS and not item.writes for item in others)
    arguments = " ".join(argument for item in commands for argument in item.arguments)
    return CommandLine(source, _is_single_call(source, commands), hides_code, changes, moves, arguments)


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
    # bash runs an exported function, passed as BASH_FUNC_<name>%%, before a builtin of the same name.
    if any(key.startswith(f"BASH_FUNC_{name}") for key in os.environ):
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
    return heredoc_only and _is_system_program(name)


def _is_system_program(name: str) -> bool:
    """Whether PATH finds the program outside the working tree in a place the user cannot write.

    echo and printf are shell builtins and never looked up; cat is, so a planted ./cat on PATH must not pass.
    """
    found = shutil.which(name)
    if found is None or not Path(found).is_absolute():
        return False
    resolved = Path(found).resolve()
    writable = os.access(resolved, os.W_OK) or os.access(resolved.parent, os.W_OK)
    return not writable and not resolved.is_relative_to(Path.cwd().resolve())


def load(path: Path, trusted: Path, secret_patterns: Path) -> GhRules:
    """Load the policy table and trusted owners at the boundary."""
    return GhRules(gh_catalog.load(path), trusted_owners.load(trusted), secret_patterns)


def is_gh(command: shell_syntax.Command) -> bool:
    """Whether the canonical command runs gh."""
    return not command.program_is_dynamic and command.arguments[0] == PROGRAM


def verdict(candidate: shell_syntax.Command, line: CommandLine, rules: GhRules) -> Verdict:
    """Allow a gh call a grant covers and that sends no secret; ask for every other one."""
    preview = shell_syntax.command_preview(candidate.raw)
    call = _judged_call(candidate, line, rules)
    if isinstance(call, str):
        return _ask(call, preview)
    if problem := _ungranted(call, line, rules):
        return _ask(f"'{call.label}' {problem}", preview, call.label)
    text = "\n".join([_sent_text(call, line), line.arguments])
    match = secret_content.first_match(text, rules.secret_patterns)
    if match is None:
        return hook_decision.ALLOW
    return _ask(f"{match.message} ({match.name}) in what this gh call sends to GitHub", preview, call.label)


def _judged_call(candidate: shell_syntax.Command, line: CommandLine, rules: GhRules) -> GhCall | str:
    """The classified call with its standard input resolved, or why the guard cannot judge it."""
    configured_repository = os.environ.get("GH_REPO")
    foreign_repository = configured_repository and gh_repository.repository(configured_repository) is None
    if os.environ.get("GH_HOST", GITHUB_HOST).lower() != GITHUB_HOST or foreign_repository:
        return "the environment sends gh to another host than github.com"
    if line.hides_code:
        return "zsh may evaluate a subscript or assignment on this line as code the guard cannot see"
    if line.changes_environment:
        return "the line sets variables or an environment that may change where gh goes"
    call = gh_invocation.classify(candidate, rules.catalog, single_call=line.single_call)
    if isinstance(call, Unclassified):
        return f"cannot classify this gh call: {call.reason}"
    stdin = _with_stdin(call, candidate)
    if isinstance(stdin, str):
        return f"this gh call {stdin or 'reads its body from a pipe or terminal'}"
    return _with_expanded_paths(stdin) if line.single_call else stdin


def _with_expanded_paths(call: GhCall) -> GhCall:
    """Scan each run-time path the harness environment expands to a readable file; the rest stay unscanned.

    On a line that is one call nothing assigns a variable, so the hook's environment gives the shell's.
    """
    expanded = {source: _expanded_path(source) for source in call.unscanned_files}
    readable = tuple(path for path in expanded.values() if path is not None)
    unscanned = tuple(source for source, path in expanded.items() if path is None)
    return replace(call, files=(*call.files, *readable), unscanned_files=unscanned)


def _expanded_path(source: str) -> str | None:
    """The file a run-time path names after quote removal and plain parameter expansion, when it exists."""
    if UNEXPANDABLE_PATH.search(source):
        return None
    expanded = shell_expanded(source)
    return expanded if expanded and Path(expanded).exists() else None


def shell_expanded(source: str) -> str:
    """A word's text as the shell builds it: single-quoted parts kept, plain parameters elsewhere expanded."""
    return "".join(
        part[1:-1] if part.startswith("'") else _expand_parameters(part.strip('"'))
        for part in SHELL_PART.findall(source)
    )


def _expand_parameters(text: str) -> str:
    return PLAIN_PARAMETER.sub(lambda match: _shell_value(match[1] or match[2]), text)


def _run_time_path_problem(sources: tuple[str, ...]) -> str:
    """Why a sent path known only at run time cannot be left unscanned, or an empty string."""
    if any(re.search(r"\$\(|`", source) for source in sources):
        return "sends a file whose path a command computes"
    if any(UNEXPANDABLE_PATH.search(source) for source in sources):
        return "sends a file whose path the guard cannot expand as the shell does"
    if any(_names_special_input(shell_expanded(source)) for source in sources):
        return "sends standard input or a device through a path named at run time"
    return ""


def _names_special_input(path: str) -> bool:
    """Whether an expanded path is gh's standard input marker or a device or process file."""
    if not path:
        return False
    try:
        return gh_invocation.sent_path(path) == "-"
    except gh_options.UnclassifiableError:
        return True


def _shell_value(name: str) -> str:
    """What a plain parameter holds in a shell started in the hook's directory with the hook's environment."""
    return str(Path.cwd()) if name == "PWD" else os.environ.get(name, "")


def _ask(reason: str, preview: str, operation: str = "") -> Verdict:
    return hook_decision.ask(f"Needs review: {reason}.\n\nCommand: {preview}", f"gh {operation}".strip())


def _ungranted(call: GhCall, line: CommandLine, rules: GhRules) -> str:
    """Why no grant allows the call where it acts, or an empty string when one does."""
    if call.reads_working_repository and (line.changes_directory or not _remotes_on_github()):
        return "reads a repository whose host the working directory's remotes may not keep on github.com"
    target = _target(call, line, rules.trusted)
    if not all(rules.catalog.grant(target, operation, call.effect) for operation in call.operations):
        return IRREVERSIBLE_REASON if call.effect is Effect.IRREVERSIBLE else TARGET_REASONS[target]
    if problem := _file_problem(call, line):
        return problem
    if call.unscanned_files and (call.effect is Effect.READ or target is not TargetClass.TRUSTED):
        return "sends input the guard cannot read to a target outside the trusted owners"
    return ""


def _file_problem(call: GhCall, line: CommandLine) -> str:
    """Why the files a call sends cannot be scanned as they will be sent, or an empty string."""
    if (call.files or call.unscanned_files) and not line.single_call:
        return "sends a file another command on the line may write after the guard reads it"
    if problem := _run_time_path_problem(call.unscanned_files):
        return problem
    paths = [Path(name) for name in call.files]
    if any(_is_irregular(path) for path in paths):
        return "sends a FIFO, device, or other file that is not a regular file"
    if any(_exceeds_scan(path) for path in paths):
        return "sends a file larger than the secret scan reads"
    return ""


def _with_stdin(call: GhCall, candidate: shell_syntax.Command) -> GhCall | str:
    """The call with what its standard input sends, or why the guard cannot read that input.

    Input written in the line, a heredoc or herestring without expansions, is part of the scanned
    line; one literal file is scanned; a file named at run time counts as unscanned, as a body file
    would. Expanded input, a descriptor copy, several redirections, or a pipe cannot be read.
    """
    if not call.reads_stdin:
        return call
    redirects = input_redirects(candidate)
    if len(redirects) != 1:
        return "reads its body from input the guard cannot see" if redirects else ""
    redirect = redirects[0].removeprefix("0")
    if redirect.startswith("<<"):
        expands = not QUOTED_HEREDOC.match(redirect) and re.search(r"[$`\\]", candidate.trailer)
        return "sends input that expands at run time" if expands else call
    if match := INPUT_FILE.match(redirect):
        return _with_stdin_file(call, match[1])
    if RUN_TIME_FILE.match(redirect):
        return replace(call, unscanned_files=(*call.unscanned_files, redirect.removeprefix("<").strip()))
    return "reads its body from input the guard cannot see"


def _with_stdin_file(call: GhCall, name: str) -> GhCall | str:
    """The call with a literal file its standard input reads, judged like any sent file path.

    The redirect's text is the shell's own, so a leading `~/` is the home directory, as the shell expands it.
    """
    try:
        path = gh_invocation.sent_path(str(Path(name).expanduser()))
    except (gh_options.UnclassifiableError, RuntimeError) as error:
        return f"cannot send its standard input: {error}"
    if path == "-":
        return "reads its body from the shell's own standard input"
    return replace(call, files=(*call.files, path))


def input_redirects(command: shell_syntax.Command) -> list[str]:
    """Each input redirection in a call's trailer, as written.

    Any extra operator counts, even one joined to a quoted heredoc delimiter, so a later redirection
    cannot hide behind the first.
    """
    first_line = command.trailer.split("\n", 1)[0]
    found = [match[1] for match in INPUT_REDIRECT.finditer(first_line)]
    operators = INPUT_OPERATOR.findall(QUOTED_TEXT.sub("Q", first_line))
    return found if len(operators) == len(found) else [*found, *operators[len(found) :]]


def _target(call: GhCall, line: CommandLine, trusted: trusted_owners.TrustedOwners) -> TargetClass:
    """Where a write acts; a read or local change is judged as acting on a trusted target, which it does not need.

    gh resolves the repository of the working directory at run time, so the guard resolves it only
    for a call that is the whole line: nothing on it can change the directory, remotes, or GH_REPO.
    """
    if call.effect in {Effect.READ, Effect.LOCAL}:
        return TargetClass.TRUSTED
    if call.unknown_target or os.environ.get("GH_HOST", GITHUB_HOST).lower() != GITHUB_HOST:
        return TargetClass.UNRESOLVED
    if call.node:
        return TargetClass.NODE
    repositories = call.repositories
    if call.implicit:
        repositories = _working_repositories() if line.single_call else ()
    if not repositories:
        return TargetClass.UNRESOLVED
    repositories = (*repositories, *call.related)
    owners_trusted = all(repository.owner.lower() in trusted.owners for repository in repositories)
    return TargetClass.TRUSTED if owners_trusted else TargetClass.UNTRUSTED


def _working_repositories() -> tuple[Repository, ...]:
    """Every repository gh may pick for the working directory: GH_REPO, or each remote as git resolves it.

    A remote whose URL does not name a github.com repository leaves the target unresolved, since gh
    may still map it to one through an ssh alias or a URL rewrite the guard does not follow.
    """
    if configured := os.environ.get("GH_REPO"):
        repository = gh_repository.repository(configured)
        return (repository,) if repository else ()
    urls = _remote_urls()
    if urls is None:
        return ()
    origins = [trusted_owners.parse_origin(url) for url in urls]
    resolved = [gh_repository.repository(value) for value in _resolved_defaults()]
    if None in origins or None in resolved:
        return ()
    return (*(Repository(owner, name) for owner, name in filter(None, origins)), *filter(None, resolved))


def _remotes_on_github() -> bool:
    """Whether every remote of the working directory, and its gh default, names a github.com repository."""
    urls = _remote_urls()
    if urls is None:
        return False
    origins_known = all(trusted_owners.parse_origin(url) for url in urls)
    return origins_known and all(gh_repository.repository(value) for value in _resolved_defaults())


def _remote_urls() -> set[str] | None:
    """Each remote URL as git resolves it, insteadOf rewrites applied; None when git cannot be asked."""
    try:
        output = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return None
    return {line.split()[1] for line in output.splitlines() if len(line.split()) >= 2}


def _resolved_defaults() -> list[str]:
    """Each repository `gh repo set-default` named in a remote's gh-resolved setting, other than `base`."""
    try:
        output = subprocess.run(
            ["git", "config", "--get-regexp", r"^remote\..*\.gh-resolved$"],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return ["unreadable"]
    values = [line.split(" ", 1)[-1].strip() for line in output.splitlines()]
    # `base` makes the fork's parent the default, which no local setting names, so it stays unresolved.
    return [value if value != "base" else "parent of a fork" for value in values]


def _sent_text(call: GhCall, line: CommandLine) -> str:
    """The command text, inline bodies and heredocs included, and the start of each literal file the call sends."""
    # A line reaching here assigns nothing, so each plain parameter holds the harness environment's value.
    expanded = _expand_parameters(line.source)
    return "\n".join([line.source, expanded, *(_file_head(Path(name)) for name in call.files)])


def _is_irregular(path: Path) -> bool:
    """Whether a path exists but is not a regular file; opening a FIFO would block the hook and drain gh's input."""
    return path.exists() and not path.is_file()


def _exceeds_scan(path: Path) -> bool:
    """Whether a regular file is longer than the part the secret scan reads."""
    return path.is_file() and path.stat().st_size > SENT_FILE_LIMIT_BYTES


def _file_head(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as stream:
            return stream.read(SENT_FILE_LIMIT_BYTES).decode(errors="replace")
    except OSError:
        return ""
