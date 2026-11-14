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
DIRECTORY_CHANGES = frozenset({"cd", "pushd", "popd"})
# Variables through which gh picks another repository or host than the call shows.
TARGET_VARIABLES = re.compile(r"\bGH_(?:REPO|HOST|ENTERPRISE_TOKEN)\b")
# zsh evaluates a subscript, and a value assigned to an integer variable, as arithmetic that may run a
# command substitution the parse never sees: `$name[...]` outside single quotes, or an assignment whose
# value, quoted in any way, holds `[...$(`.
SUBSCRIPT = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\[")
ARITHMETIC_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*\[[^\]]*\$\(")
SENT_FILE_LIMIT_BYTES = 100000
REMOTE_LOOKUP_TIMEOUT_SECONDS = 5
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
    """The whole command a gh call runs in, which decides how far its words and directory can be trusted."""

    source: str
    commands: tuple[shell_syntax.Command, ...]

    @property
    def single_call(self) -> bool:
        """Whether the line is one call with no assignment, so every variable comes from the harness."""
        if len(self.commands) != 1 or self.commands[0].wrapper_depth:
            return False
        statements = shell_syntax.syntax_tree(self.source).get("Stmts", [])
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

    @property
    def evaluates_hidden_code(self) -> bool:
        """Whether zsh may run a command substitution inside a subscript or an arithmetic assignment."""
        outside = shell_inspection.text_outside_single_quotes(self.source)
        return bool(SUBSCRIPT.search(outside) or ARITHMETIC_ASSIGNMENT.search(self.source))

    @property
    def keeps_directory(self) -> bool:
        """Whether gh runs unwrapped in the hook's working directory, picking the repository the hook can see."""
        names = {Path(item.arguments[0]).name for item in self.commands}
        wrapped = any(item.wrapper_depth for item in self.commands)
        return not (wrapped or names & DIRECTORY_CHANGES or TARGET_VARIABLES.search(self.source))


def load(path: Path, trusted: Path, secret_patterns: Path) -> GhRules:
    """Load the policy table and trusted owners at the boundary."""
    return GhRules(gh_catalog.load(path), trusted_owners.load(trusted), secret_patterns)


def is_gh(command: shell_syntax.Command) -> bool:
    """Whether the canonical command runs gh."""
    return not command.program_is_dynamic and command.arguments[0] == PROGRAM


def verdict(candidate: shell_syntax.Command, line: CommandLine, rules: GhRules) -> Verdict:
    """Allow a gh call a grant covers and that sends no secret; ask for every other one."""
    preview = shell_syntax.command_preview(candidate.raw)
    if line.evaluates_hidden_code:
        return hook_decision.ask(
            f"Needs review: zsh may evaluate a subscript or assignment on this line as code the guard cannot see."
            f"\n\nCommand: {preview}",
            PROGRAM,
        )
    call = gh_invocation.classify(candidate, rules.catalog, single_call=line.single_call)
    if isinstance(call, Unclassified):
        return hook_decision.ask(
            f"Needs review: cannot classify this gh call: {call.reason}.\n\nCommand: {preview}", PROGRAM
        )
    target = _target(call, line, rules.trusted)
    if not all(rules.catalog.grant(target, operation, call.effect) for operation in call.operations):
        reason = (
            "cannot be taken back or promotes work (class D)"
            if call.effect is Effect.IRREVERSIBLE
            else TARGET_REASONS[target]
        )
        return hook_decision.ask(f"Needs review: '{call.label}' {reason}.\n\nCommand: {preview}", f"gh {call.label}")
    if call.effect in {Effect.READ, Effect.LOCAL} and not call.files:
        return hook_decision.ALLOW
    match = secret_content.first_match(_sent_text(call, line), rules.secret_patterns)
    if match is None:
        return hook_decision.ALLOW
    return hook_decision.ask(
        f"Needs review: {match.message} ({match.name}) in what this gh call sends to GitHub.\n\nCommand: {preview}",
        f"gh {call.label}",
    )


def _target(call: GhCall, line: CommandLine, trusted: trusted_owners.TrustedOwners) -> TargetClass:
    """Where a write acts; a read or local change is judged as acting on a trusted target, which it does not need."""
    if call.effect in {Effect.READ, Effect.LOCAL}:
        return TargetClass.TRUSTED
    if call.unknown_target:
        return TargetClass.UNRESOLVED
    if call.node:
        return TargetClass.NODE
    repositories = call.repositories
    if call.implicit:
        if not line.keeps_directory:
            return TargetClass.UNRESOLVED
        repositories = _working_repositories()
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
