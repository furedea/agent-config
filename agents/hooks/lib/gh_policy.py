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

import gh_catalog
import gh_invocation
import gh_options
import gh_repository
import hook_decision
import secret_content
import shell_syntax
import trusted_owners
from gh_catalog import Catalog, Effect, TargetClass
from gh_command_line import (
    PROGRAM,
    QUOTED_HEREDOC,
    CommandLine,
    has_inherited_function,
    has_writable_path_entry_before,
    input_redirects,
    is_outside_agent_roots,
)
from gh_invocation import GhCall, Unclassified
from gh_repository import Repository
from hook_decision import Verdict

SENT_FILE_LIMIT_BYTES = 100000
REMOTE_LOOKUP_TIMEOUT_SECONDS = 5
GITHUB_HOST = "github.com"
# Input redirections in a call's trailer: a heredoc whose delimiter is quoted keeps its body literal
# and in the line; a file is read at run time; anything else, a herestring, an unquoted heredoc, or a
# descriptor copy, may carry text the guard cannot read.
INPUT_FILE = re.compile(r"^<\s*((?:~/)?[^\s$`'\"\\*?\[<>&(~][^\s$`'\"\\*?\[<>&(]*)$")
# A file named by a quoted parameter, which stays one path and is read like a body file named at run time.
RUN_TIME_FILE = re.compile(r'^<\s*"[^"`]*\$[^"`]*"$')
# A run-time path the guard would expand differently from the shell: a glob, substitution, tilde,
# escape, parameter operator or subscript, or a zsh modifier such as `$f:h`.
UNEXPANDABLE_PATH = re.compile(r"[`*?\[~\\]|\$\(|\$\{[^}]*[^A-Za-z0-9_}]|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?:")
# A word's single-quoted, double-quoted, and bare parts, in order.
SHELL_PART = re.compile(r"""'[^']*'|"[^"]*"|[^'"]+""")
# A plain parameter in a run-time path; one the environment lacks expands to nothing, as in the shell.
PLAIN_PARAMETER = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})")
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


def load(path: Path, trusted: Path, secret_patterns: Path) -> GhRules:
    """Load the policy table and trusted owners at the boundary."""
    return GhRules(gh_catalog.load(path), trusted_owners.load(trusted), secret_patterns)


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
    if problem := _environment_problem(line):
        return problem
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


def _environment_problem(line: CommandLine) -> str:
    """Why the environment may run something else than gh against github.com, or an empty string."""
    # gh runs git for clones, checkouts, and to find the working repository, so git must be as safe as gh.
    for name in (PROGRAM, "git"):
        if problem := _stand_in_problem(name, line):
            return problem
    if os.environ.get("GH_FORCE_TTY"):
        return "the environment forces a terminal, so gh would start the pager program it names"
    configured_repository = os.environ.get("GH_REPO")
    foreign_repository = configured_repository and gh_repository.repository(configured_repository) is None
    if os.environ.get("GH_HOST", GITHUB_HOST).lower() != GITHUB_HOST or foreign_repository:
        return "the environment sends gh to another host than github.com"
    return ""


def _stand_in_problem(name: str, line: CommandLine) -> str:
    """Why something else than the installed program may run under its name, or an empty string."""
    if not line.single_call and has_writable_path_entry_before(name):
        return f"another command on the line could place a {name} earlier on PATH"
    if has_inherited_function(name):
        return f"the environment carries a shell function that bash would run instead of {name}"
    if not is_outside_agent_roots(name):
        return f"PATH finds a {name} in a directory the agent can write"
    return ""


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
    output = _git_output("remote", "-v")
    if output is None:
        return None
    return {line.split()[1] for line in output.splitlines() if len(line.split()) >= 2}


def _resolved_defaults() -> list[str]:
    """Each repository a remote's gh-resolved setting names; `base` points at that remote itself."""
    output = _git_output("config", "--get-regexp", r"^remote\..*\.gh-resolved$")
    if output is None:
        return ["unreadable"]
    values = [line.split(" ", 1)[-1].strip() for line in output.splitlines()]
    # `base` marks the remote it is set on, whose URL is already among the remotes.
    return [value for value in values if value != "base"]


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


def _git_output(*arguments: str) -> str | None:
    """What git prints for the arguments, or None when git cannot be asked or PATH finds one the agent can write.

    A planted git could tell the guard one remote and gh another, and would run inside the hook itself.
    """
    found = shutil.which("git")
    if found is None or not is_outside_agent_roots("git"):
        return None
    try:
        return subprocess.run(
            [found, *arguments],
            capture_output=True,
            text=True,
            timeout=REMOTE_LOOKUP_TIMEOUT_SECONDS,
            check=False,
        ).stdout
    except OSError, subprocess.SubprocessError:
        return None
