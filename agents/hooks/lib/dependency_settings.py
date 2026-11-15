"""Ask when a uv dependency change may escape the project or the package-age limit.

uv dependency changes run unprompted because they rewrite only the project's manifest and lock file,
and the user's uv configuration refuses versions younger than a week. An option, an environment
variable, a project setting, a directory change, or a file write in the same command can lift that
limit or point uv at another project, and the parsed words alone do not show most of them. A URL,
a git reference, a local path, or another index carries no upload time the limit could judge.
"""

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import command_policy
import hook_decision
import session_snapshot
import shell_inspection
import shell_syntax
from hook_decision import Verdict

PROGRAM = "uv"
SUBCOMMANDS = frozenset({"add", "lock"})
# The only options a dependency change may carry unprompted, by whether each takes a name as its value;
# any other option could point uv at another project, configuration, index, or source.
FLAGS = frozenset({"--no-sync", "--frozen", "--locked", "--upgrade", "-U", "--quiet", "-q", "--verbose", "-v"})
NAMED_OPTIONS = frozenset({"--group", "--optional", "--extra", "--upgrade-package", "-P"})
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# A registry requirement: a name, optional extras, and version specifiers, with no marker, URL, or path.
SPECIFIER = r"(===|==|!=|~=|>=|<=|>|<)[A-Za-z0-9.*+!_-]+"
REQUIREMENT = re.compile(rf"{NAME.pattern}(\[[A-Za-z0-9._,-]+\])?({SPECIFIER}(,{SPECIFIER})*)?")
# Project files and the uv settings in them that replace the user's limit or add a package source.
PROJECT_SETTINGS = ("pyproject.toml", "uv.toml")
OVERRIDING_SETTINGS = frozenset(
    {"exclude-newer", "exclude-newer-package", "index", "index-url", "extra-index-url", "find-links", "sources"}
    | {"no-index", "index-strategy", "no-build-isolation", "config-settings", "dependency-metadata"}
)
# Programs that may share the command: none moves the directory, sets variables, or writes files.
COMPANIONS = frozenset({PROGRAM, "echo", "printf", "true", "false", "test", "[", "ls", "cat", "pwd", "stat"})
# Declarations the parser keeps out of its commands, which set variables for the rest of the command.
DECLARATION = re.compile(r"(^|[\s;&|(){}`])(export|declare|typeset|readonly|local)(\s|$)")
# An assignment where a command word can start, which `set -a` or a later export hands to uv.
ASSIGNMENT = re.compile(r"(^|[;&|(){}`\n])\s*[A-Za-z_][A-Za-z0-9_]*\+?=")


def objection(payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when a uv dependency change names another place, lifts the age limit, or shares settings."""
    changes = [item for item in commands if _is_dependency_change(item)]
    if not changes:
        return hook_decision.ALLOW
    reason = _argument_reason(changes) or _neighbour_reason(command, commands, changes) or _project_reason(payload)
    if not reason:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(changes[0].raw)
    return hook_decision.ask(f"Needs review: a uv dependency change {reason}.\n\nCommand: {preview}", PROGRAM)


def _argument_reason(changes: list[shell_syntax.Command]) -> str:
    """Why the dependency change's own words may escape the project or the age limit; unknown words ask."""
    for item in changes:
        words = iter(zip(item.arguments[2:], item.dynamic[2:], strict=True))
        if word := next((word for word, dynamic in words if not _is_known_word(word, dynamic, words)), ""):
            return f"names '{word}', which may lift the package-age limit or point uv elsewhere"
    return ""


def _is_known_word(word: str, dynamic: bool, rest: Iterator[tuple[str, bool]]) -> bool:
    """Whether the word is a listed flag, a listed option with a plain name, or a registry requirement.

    A listed option without `=` takes the next word from `rest` as its value.
    """
    if dynamic:
        return False
    if word in FLAGS:
        return True
    option, attached, value = word.partition("=")
    if option in NAMED_OPTIONS:
        value, dynamic = (value, False) if attached else next(rest, ("", True))
        return not dynamic and bool(REQUIREMENT.fullmatch(value))
    return not word.startswith("-") and bool(REQUIREMENT.fullmatch(word))


def _neighbour_reason(
    command: str, commands: tuple[shell_syntax.Command, ...], changes: list[shell_syntax.Command]
) -> str:
    """Why the rest of the command may change uv's environment, directory, or settings before it runs."""
    text = shell_inspection.text_outside_single_quotes(command)
    if DECLARATION.search(text) or ASSIGNMENT.search(text) or any(_has_assignment(item) for item in changes):
        return "runs beside environment settings the guard cannot read"
    if any(item.wrapper_depth for item in changes) or not all(_is_companion(item) for item in commands):
        return "shares the command with a program that may change its directory or settings"
    if any(item.writes or item.trailer for item in commands):
        return "shares the command with a write that may change the project's settings first"
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
            return f"runs in a project whose settings replace the package-age limit or its sources ({folder})"
        if folder == root:
            break
    return ""


def _sets_age_limit(path: Path) -> bool:
    """Whether the file sets a uv setting that overrides the limit or a source, at the top or under tool.uv.

    A file that cannot be read or parsed counts, since uv may still read it differently.
    """
    try:
        settings = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return False
    except OSError, UnicodeDecodeError, tomllib.TOMLDecodeError:
        return True
    tool = settings.get("tool")
    tables = (settings, tool.get("uv") if isinstance(tool, dict) else None)
    return any(isinstance(table, dict) and not OVERRIDING_SETTINGS.isdisjoint(table) for table in tables)


def _is_dependency_change(item: shell_syntax.Command) -> bool:
    arguments = command_policy.canonical(item).arguments
    return arguments[0] == PROGRAM and len(arguments) > 1 and arguments[1] in SUBCOMMANDS


def _is_companion(item: shell_syntax.Command) -> bool:
    name = Path(item.arguments[0]).name
    return not item.program_is_dynamic and item.arguments[0] == name and name in COMPANIONS


def _has_assignment(item: shell_syntax.Command) -> bool:
    return not item.raw.lstrip().startswith(item.words[0])
