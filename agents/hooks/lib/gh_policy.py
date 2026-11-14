"""Judge each gh call by its effect: classify it, find where it acts, and look the pair up in the gh policy table.

A read, or a change to the local checkout only, runs on any repository. A write runs unprompted
only when a grant covers its operation on the target class; every other write asks, as does any
call the guard cannot classify. What a granted call sends to GitHub is scanned for secrets first.
"""

import os
import re
import subprocess
from dataclasses import dataclass
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
HOST_VARIABLES = re.compile(r"\bGH_(?:HOST|REPO|ENTERPRISE_TOKEN)\b")
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
    `hides_code` says zsh may run a command substitution inside a subscript or arithmetic assignment.
    """

    source: str
    single_call: bool
    hides_code: bool


def command_line(source: str, commands: tuple[shell_syntax.Command, ...]) -> CommandLine:
    """Read the line's shape once; it parses the source again, so build it only for a line holding gh."""
    outside = shell_inspection.text_outside_single_quotes(source)
    hides_code = bool(SUBSCRIPT.search(outside) or ARITHMETIC_ASSIGNMENT.search(source))
    return CommandLine(source, _is_single_call(source, commands), hides_code)


def _is_single_call(source: str, commands: tuple[shell_syntax.Command, ...]) -> bool:
    """One statement holding one call; any other command only prints text into its words."""
    head, *substituted = commands
    if head.wrapper_depth or not all(_only_prints(item) for item in substituted):
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
    """Whether a command inside a substitution only prints text, such as a body through a quoted heredoc."""
    name = Path(command.arguments[0]).name
    return name in PRINTING_PROGRAMS and not (command.wrapper_depth or command.writes or command.program_is_dynamic)


def load(path: Path, trusted: Path, secret_patterns: Path) -> GhRules:
    """Load the policy table and trusted owners at the boundary."""
    return GhRules(gh_catalog.load(path), trusted_owners.load(trusted), secret_patterns)


def is_gh(command: shell_syntax.Command) -> bool:
    """Whether the canonical command runs gh."""
    return not command.program_is_dynamic and command.arguments[0] == PROGRAM


def verdict(candidate: shell_syntax.Command, line: CommandLine, rules: GhRules) -> Verdict:
    """Allow a gh call a grant covers and that sends no secret; ask for every other one."""
    preview = shell_syntax.command_preview(candidate.raw)
    if line.hides_code:
        return _ask("zsh may evaluate a subscript or assignment on this line as code the guard cannot see", preview)
    if HOST_VARIABLES.search(line.source):
        return _ask("the line names a variable that sends gh to another host or repository", preview)
    call = gh_invocation.classify(candidate, rules.catalog, single_call=line.single_call)
    if isinstance(call, Unclassified):
        return _ask(f"cannot classify this gh call: {call.reason}", preview)
    if problem := _ungranted(call, line, rules):
        return _ask(f"'{call.label}' {problem}", preview, call.label)
    match = secret_content.first_match(_sent_text(call, line), rules.secret_patterns)
    if match is None:
        return hook_decision.ALLOW
    return _ask(f"{match.message} ({match.name}) in what this gh call sends to GitHub", preview, call.label)


def _ask(reason: str, preview: str, operation: str = "") -> Verdict:
    return hook_decision.ask(f"Needs review: {reason}.\n\nCommand: {preview}", f"gh {operation}".strip())


def _ungranted(call: GhCall, line: CommandLine, rules: GhRules) -> str:
    """Why no grant allows the call where it acts, or an empty string when one does."""
    target = _target(call, line, rules.trusted)
    if not all(rules.catalog.grant(target, operation, call.effect) for operation in call.operations):
        return IRREVERSIBLE_REASON if call.effect is Effect.IRREVERSIBLE else TARGET_REASONS[target]
    if (call.files or call.unscanned_files) and not line.single_call:
        return "sends a file another command on the line may write after the guard reads it"
    return ""


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
    """Every GitHub repository gh may pick for the working directory: GH_REPO, or each GitHub remote."""
    if configured := os.environ.get("GH_REPO"):
        repository = gh_invocation.repository(configured)
        return (repository,) if repository else ()
    try:
        output = subprocess.run(
            ["git", "config", "--get-regexp", r"^remote\..*\.url$"],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return ()
    origins = (trusted_owners.parse_origin(line.split(" ", 1)[-1]) for line in output.splitlines())
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
