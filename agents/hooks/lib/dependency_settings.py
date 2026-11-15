"""Ask when a uv dependency change may escape the project or the package-age limit.

uv dependency changes run unprompted because they rewrite only the project's manifest and lock file,
and the user's uv configuration refuses versions younger than a week. An option, an environment
variable, a project setting, or a directory change in the same command can lift that limit or
point uv at another project, and the parsed words alone do not show the last three.
"""

import re
from pathlib import Path

import command_policy
import hook_decision
import session_snapshot
import shell_inspection
import shell_syntax
from hook_decision import Verdict

PROGRAM = "uv"
SUBCOMMANDS = frozenset({"add", "lock"})
# Options that point uv at another project, script, or configuration.
LOCATION_OPTIONS = frozenset({"--project", "--directory", "--script", "--config-file"})
# Options that lift or replace the configured package-age limit.
AGE_OPTIONS = frozenset({"--exclude-newer", "--exclude-newer-package", "--no-config"})
# Project files whose `exclude-newer` replaces the user's limit.
PROJECT_SETTINGS = ("pyproject.toml", "uv.toml")
AGE_SETTING = "exclude-newer"
# Programs that may share the command: none moves the directory, sets variables, or writes settings.
COMPANIONS = frozenset({PROGRAM, "git", "echo", "printf", "true", "false", "test", "[", "ls", "cat", "pwd", "stat"})
# Declarations the parser keeps out of its commands, which set variables for the rest of the command.
DECLARATION = re.compile(r"(^|[\s;&|(){}`])(export|declare|typeset|readonly|local)(\s|$)")
# An assignment where a command word can start, which `set -a` or a later export hands to uv.
ASSIGNMENT = re.compile(r"(^|[;&|(){}`\n])\s*[A-Za-z_][A-Za-z0-9_]*\+?=")


def objection(payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when a uv dependency change names another place, lifts the age limit, or shares settings."""
    changes = [item for item in commands if _is_dependency_change(item)]
    if not changes:
        return hook_decision.ALLOW
    reason = _command_reason(command, commands, changes) or _project_reason(payload)
    if not reason:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(changes[0].raw)
    return hook_decision.ask(f"Needs review: a uv dependency change {reason}.\n\nCommand: {preview}", PROGRAM)


def _command_reason(
    command: str, commands: tuple[shell_syntax.Command, ...], changes: list[shell_syntax.Command]
) -> str:
    options = {word.partition("=")[0] for item in changes for word in item.arguments[1:]}
    if options & LOCATION_OPTIONS:
        return "names another project, script, or configuration"
    if options & AGE_OPTIONS:
        return "replaces the package-age limit"
    text = shell_inspection.text_outside_single_quotes(command)
    if DECLARATION.search(text) or ASSIGNMENT.search(text) or any(_has_assignment(item) for item in changes):
        return "runs beside environment settings the guard cannot read"
    if any(item.wrapper_depth for item in changes) or not all(_is_companion(item) for item in commands):
        return "shares the command with a program that may change its directory or settings"
    return ""


def _project_reason(payload: dict) -> str:
    """A project setting the session may have written replaces the user's limit, so it asks too."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return "runs from an unknown working directory"
    directory = Path(cwd).resolve()
    try:
        root = session_snapshot.repository_root(directory)
    except session_snapshot.SnapshotError:
        return "runs outside a repository"
    for folder in (directory, *directory.parents):
        if any(_sets_age_limit(folder / name) for name in PROJECT_SETTINGS):
            return f"runs in a project whose settings replace the package-age limit ({folder})"
        if folder == root:
            break
    return ""


def _sets_age_limit(path: Path) -> bool:
    try:
        return AGE_SETTING in path.read_text(errors="replace")
    except OSError:
        return False


def _is_dependency_change(item: shell_syntax.Command) -> bool:
    arguments = command_policy.canonical(item).arguments
    return arguments[0] == PROGRAM and len(arguments) > 1 and arguments[1] in SUBCOMMANDS


def _is_companion(item: shell_syntax.Command) -> bool:
    name = Path(item.arguments[0]).name
    return not item.program_is_dynamic and item.arguments[0] == name and name in COMPANIONS


def _has_assignment(item: shell_syntax.Command) -> bool:
    return not item.raw.lstrip().startswith(item.words[0])
