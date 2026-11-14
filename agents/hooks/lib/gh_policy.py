"""Judge each gh call by its effect: classify it, find where it acts, and look the pair up in the gh policy table.

A read, or a change to the local checkout only, runs on any repository. A write runs unprompted
only when a grant covers its operation on the target class; every other write asks, as does any
call the guard cannot classify. What a granted call sends to GitHub is scanned for secrets first.
"""

import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import gh_catalog
import gh_invocation
import hook_decision
import secret_content
import shell_inspection
import shell_syntax
import trusted_owners
from gh_catalog import Catalog, Effect, TargetClass
from gh_invocation import GhCall, Repository, Unclassified
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
# Variables through which gh picks another host or repository than its words show; the hook's own
# environment is the harness's, but one set on the line comes from the agent.
GH_VARIABLE = r"(?:(?:GH|GITHUB|GIT)_[A-Z_]+|XDG_CONFIG_HOME)"
# An assignment in the source, or an argument that is the variable itself or assigns it after quote
# removal, as `export`, `read`, or `env` take it; a name inside prose is neither.
ASSIGNED_VARIABLE = re.compile(rf"(?:^|[\s;&|(]){GH_VARIABLE}\+?=")
VARIABLE_ARGUMENT = re.compile(rf"{GH_VARIABLE}(?:\+?=.*)?", re.DOTALL)
# Input redirections in a call's trailer: a heredoc whose delimiter is quoted keeps its body literal
# and in the line; a file is read at run time; anything else, a herestring, an unquoted heredoc, or a
# descriptor copy, may carry text the guard cannot read.
QUOTED_HEREDOC = re.compile(r"""^<<-?\s*(?:'[^']+'|"[^"]+"|\\\w+)$""")
INPUT_FILE = re.compile(r"^<\s*((?:~/)?[^\s$`'\"\\*?\[<>&(~][^\s$`'\"\\*?\[<>&(]*)$")
# A file named by a quoted parameter, which stays one path and is read like a body file named at run time.
RUN_TIME_FILE = re.compile(r'^<\s*"[^"`]*\$[^"`]*"$')
INPUT_REDIRECT = re.compile(r"""(?:^|\s)(0?<(?:<<|<-?|>|&)?\s*(?:'[^']*'|"[^"]*"|\S+))""")
# A substitution holding only an input redirection, such as `$(< .env)`, reads that file in bash.
REDIRECT_SUBSTITUTION = re.compile(r"\$\(\s*<|`\s*<")
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
    and `redirects_gh` that the line names a variable through which gh or git picks another host,
    repository, or configuration, in its source or in any argument after quote removal.
    """

    source: str
    single_call: bool
    hides_code: bool
    redirects_gh: bool


def command_line(source: str, commands: tuple[shell_syntax.Command, ...]) -> CommandLine:
    """Read the line's shape once; it parses the source again, so build it only for a line holding gh."""
    outside = shell_inspection.text_outside_single_quotes(source)
    hides_code = bool(SUBSCRIPT.search(outside) or ARITHMETIC_ASSIGNMENT.search(source))
    redirects_gh = (
        bool(ASSIGNED_VARIABLE.search(source))
        or any(VARIABLE_ARGUMENT.fullmatch(argument) for item in commands for argument in item.arguments[1:])
        or any(_declares_gh_variable(clause) for clause in _declarations(source))
    )
    return CommandLine(source, _is_single_call(source, commands), hides_code, redirects_gh)


def _declarations(source: str) -> list[str]:
    """The text of each export, declare, local, readonly, or typeset clause, which parse does not list as a command."""
    data = source.encode()
    return [
        data[node["Pos"]["Offset"] : node["End"]["Offset"]].decode()
        for node in shell_syntax.nodes(shell_syntax.syntax_tree(source))
        if node.get("Type") == "DeclClause"
    ]


def _declares_gh_variable(clause: str) -> bool:
    """Whether a declaration names a gh variable once its quotes and escapes are removed."""
    return any(VARIABLE_ARGUMENT.fullmatch(word) for word in re.sub(r"[\"'\\]", "", clause).split())


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
    name = Path(command.arguments[0]).name
    if name not in PRINTING_PROGRAMS or command.wrapper_depth or command.writes or command.has_dynamic_words:
        return False
    if any(not QUOTED_HEREDOC.match(redirect) for redirect in input_redirects(command)):
        return False
    return name != "cat" or all(argument.startswith("-") for argument in command.arguments[1:])


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
    match = secret_content.first_match(_sent_text(call, line), rules.secret_patterns)
    if match is None:
        return hook_decision.ALLOW
    return _ask(f"{match.message} ({match.name}) in what this gh call sends to GitHub", preview, call.label)


def _judged_call(candidate: shell_syntax.Command, line: CommandLine, rules: GhRules) -> GhCall | str:
    """The classified call with its standard input resolved, or why the guard cannot judge it."""
    if line.hides_code:
        return "zsh may evaluate a subscript or assignment on this line as code the guard cannot see"
    if line.redirects_gh:
        return "the line names a variable that sends gh to another host or repository"
    call = gh_invocation.classify(candidate, rules.catalog, single_call=line.single_call)
    if isinstance(call, Unclassified):
        return f"cannot classify this gh call: {call.reason}"
    stdin = _with_stdin(call, candidate)
    if isinstance(stdin, str):
        return f"this gh call {stdin or 'reads its body from a pipe or terminal'}"
    return stdin


def _ask(reason: str, preview: str, operation: str = "") -> Verdict:
    return hook_decision.ask(f"Needs review: {reason}.\n\nCommand: {preview}", f"gh {operation}".strip())


def _ungranted(call: GhCall, line: CommandLine, rules: GhRules) -> str:
    """Why no grant allows the call where it acts, or an empty string when one does."""
    target = _target(call, line, rules.trusted)
    if not all(rules.catalog.grant(target, operation, call.effect) for operation in call.operations):
        return IRREVERSIBLE_REASON if call.effect is Effect.IRREVERSIBLE else TARGET_REASONS[target]
    if (call.files or call.unscanned_files) and not line.single_call:
        return "sends a file another command on the line may write after the guard reads it"
    if call.unscanned_files and (call.effect is Effect.READ or target is not TargetClass.TRUSTED):
        return "sends input the guard cannot read to a target outside the trusted owners"
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
        expands = not QUOTED_HEREDOC.match(redirect) and re.search(r"[$`]", candidate.trailer)
        return "sends input that expands at run time" if expands else call
    if match := INPUT_FILE.match(redirect):
        return replace(call, files=(*call.files, match[1]))
    if RUN_TIME_FILE.match(redirect):
        return replace(call, unscanned_files=True)
    return "reads its body from input the guard cannot see"


def input_redirects(command: shell_syntax.Command) -> list[str]:
    """Each input redirection in a call's trailer, as written."""
    return [match[1] for match in INPUT_REDIRECT.finditer(command.trailer.split("\n", 1)[0])]


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
    owners_trusted = all(repository.owner.lower() in trusted.owners for repository in repositories)
    return TargetClass.TRUSTED if owners_trusted else TargetClass.UNTRUSTED


def _working_repositories() -> tuple[Repository, ...]:
    """Every repository gh may pick for the working directory: GH_REPO, or each remote as git resolves it.

    A remote whose URL does not name a github.com repository leaves the target unresolved, since gh
    may still map it to one through an ssh alias or a URL rewrite the guard does not follow.
    """
    if configured := os.environ.get("GH_REPO"):
        repository = gh_invocation.repository(configured)
        return (repository,) if repository else ()
    try:
        output = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return ()
    urls = {line.split()[1] for line in output.splitlines() if len(line.split()) >= 2}
    origins = [trusted_owners.parse_origin(url) for url in urls]
    if None in origins:
        return ()
    return tuple(Repository(owner, name) for owner, name in filter(None, origins))


def _sent_text(call: GhCall, line: CommandLine) -> str:
    """The command text, inline bodies and heredocs included, and the start of each literal file the call sends."""
    return "\n".join([line.source, *(_file_head(Path(name).expanduser()) for name in call.files)])


def _file_head(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return stream.read(SENT_FILE_LIMIT_BYTES).decode(errors="replace")
    except OSError:
        return ""
