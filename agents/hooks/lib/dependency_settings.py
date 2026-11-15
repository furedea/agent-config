"""Ask when a uv dependency change may escape the project or the package-age limit.

uv dependency changes run unprompted because they rewrite only the project's manifest and lock file,
and the user's uv configuration refuses versions younger than a week. An option, an environment
variable, a project setting, a directory change, or a file write in the same command can lift that
limit or point uv at another project, and the parsed words alone do not show most of them. A URL,
a git reference, a local path, or another index carries no upload time the limit could judge.
"""

import os
import re
import tomllib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import command_policy
import hook_decision
import session_snapshot
import shell_inspection
import shell_syntax
import system_programs
from hook_decision import Verdict

PROGRAM = "uv"
# `uv lock` changes dependencies only when it upgrades them; `--check` and the like only verify.
LOCK_UPGRADES = frozenset({"--upgrade", "--upgrade-package"})
# The only options a dependency change may carry unprompted, by whether each takes a name as its value;
# any other option could point uv at another project, configuration, index, or source.
FLAGS = frozenset(
    {
        "--no-sync",
        "--frozen",
        "--locked",
        "--upgrade",
        "-U",
        "--quiet",
        "-q",
        "--verbose",
        "-v",
        "--check",
        "--dry-run",
    }
)
NAMED_OPTIONS = frozenset({"--group", "--optional", "--extra", "--upgrade-package", "-P"})
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# A registry requirement: a name, optional extras, and version specifiers, with no marker, URL, or path.
SPECIFIER = r"(===|==|!=|~=|>=|<=|>|<)[A-Za-z0-9.*+!_-]+"
REQUIREMENT = re.compile(rf"{NAME.pattern}(\[[A-Za-z0-9._,-]+\])?({SPECIFIER}(,{SPECIFIER})*)?")
# A bare archive name, which uv reads as a local file rather than a registry name.
ARCHIVE_SUFFIXES = frozenset(
    {"whl", "zip", "egg", "tar", "gz", "tgz", "bz2", "tbz", "tbz2", "xz", "txz", "lz", "lzma", "tlz", "zst", "tzst"}
    | {"z", "7z", "rar"}
)
# A dependency entry the age limit cannot judge: a direct reference, a URL, or a path.
DIRECT_REFERENCE = re.compile(r"@|://|^\s*[./~]")
# Project files and the uv settings in them that replace the user's limit or add a package source.
PROJECT_SETTINGS = ("pyproject.toml", "uv.toml")
# The user's limit, and the variables that override any configuration file.
AGE_LIMIT = "exclude-newer"
MINIMUM_AGE = timedelta(days=7)
SPAN = re.compile(r"(?P<count>\d+)\s*(?P<unit>weeks?|days?)|p(?P<iso_count>\d+)(?P<iso_unit>[wd])")
ENVIRONMENT_PREFIX = "UV_"
DEFAULT_SYSTEM_CONFIG = "/etc/xdg"
OVERRIDING_SETTINGS = frozenset(
    {"exclude-newer", "exclude-newer-package", "index", "index-url", "extra-index-url", "find-links", "sources"}
    | {"no-index", "index-strategy", "no-build-isolation", "config-settings", "dependency-metadata"}
    | {"override-dependencies", "constraint-dependencies", "build-constraint-dependencies", "dev-dependencies"}
)
# Shell builtins that may share the command: none moves the directory, sets variables, or writes files,
# and none is looked up through an inherited PATH that could hold another program of the same name.
# uv itself counts only as a dependency change or after the last one, since `uv run` runs any program.
COMPANIONS = frozenset({"echo", "true", "false", "test", "[", "pwd"})
# Declarations the parser keeps out of its commands, which set variables for the rest of the command.
DECLARATION = re.compile(r"(^|[\s;&|(){}`])(export|declare|typeset|readonly|local)(\s|$)")
# An assignment where a command word can start, which `set -a` or a later export hands to uv.
ASSIGNMENT = re.compile(r"(^|[;&|(){}`\n])\s*[A-Za-z_][A-Za-z0-9_]*\+?=")


def objection(payload: dict, command: str, commands: tuple[shell_syntax.Command, ...]) -> Verdict:
    """Ask when a uv dependency change names another place, lifts the age limit, or shares settings."""
    if leading := next((item for item in commands if _has_option_before_subcommand(item)), None):
        preview = shell_syntax.command_preview(leading.raw)
        return hook_decision.ask(
            f"Needs review: uv takes options before its subcommand, which may point it at another project or "
            f"configuration.\n\nCommand: {preview}",
            PROGRAM,
        )
    calls = [item for item in commands if _is_dependency_call(item)]
    changes = [item for item in calls if _changes_dependencies(item)]
    reason = _argument_reason(calls)
    if changes and not reason:
        reason = (
            _neighbour_reason(command, commands, changes)
            or _program_reason(changes)
            or _environment_reason()
            or _project_reason(payload)
        )
    if not reason:
        return hook_decision.ALLOW
    preview = shell_syntax.command_preview(calls[0].raw)
    return hook_decision.ask(f"Needs review: a uv dependency change {reason}.\n\nCommand: {preview}", PROGRAM)


def _argument_reason(calls: list[shell_syntax.Command]) -> str:
    """Why a uv add or lock call's own words may escape the project or the age limit; unknown words ask."""
    for item in calls:
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
        return not dynamic and _is_registry_requirement(value)
    return not word.startswith("-") and _is_registry_requirement(word)


def _is_registry_requirement(word: str) -> bool:
    """A name, extras, and specifiers whose name does not end like an archive or compressed file."""
    match = REQUIREMENT.fullmatch(word)
    name = NAME.match(word)
    return bool(match and name) and not any(
        text.rpartition(".")[2].casefold() in ARCHIVE_SUFFIXES for text in (name.group(), word)
    )


def _neighbour_reason(
    command: str, commands: tuple[shell_syntax.Command, ...], changes: list[shell_syntax.Command]
) -> str:
    """Why the rest of the command may change uv's environment, directory, or settings before it runs."""
    text = shell_inspection.text_outside_single_quotes(command)
    if DECLARATION.search(text) or ASSIGNMENT.search(text) or any(_has_assignment(item) for item in changes):
        return "runs beside environment settings the guard cannot read"
    last = max(index for index, item in enumerate(commands) if item in changes)
    if any(item.wrapper_depth for item in changes) or not all(
        item in changes or _is_companion(item) or (index > last and _is_uv(item))
        for index, item in enumerate(commands)
    ):
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
        found = [folder / name for name in PROJECT_SETTINGS if (folder / name).exists()]
        linked = [path for path in [*found, folder / "uv.lock"] if os.path.lexists(path)]
        if any(not path.resolve().is_relative_to(root.resolve()) for path in linked if folder.is_relative_to(root)):
            return f"would write a project file in {folder} that links outside the worktree"
        if found and not folder.is_relative_to(root):
            return f"may resolve the project at {folder}, outside the worktree"
        if any(_has_overriding_settings(path) for path in found):
            return f"runs in a project whose settings replace the package-age limit or its sources ({folder})"
    return ""


def _environment_reason() -> str:
    """Inherited uv variables override every setting, and the limit holds only if the user's configuration sets it."""
    if inherited := sorted(name for name in os.environ if name.startswith(ENVIRONMENT_PREFIX)):
        return f"inherits {inherited[0]}, which may override the package-age limit or its sources"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    try:
        settings = tomllib.loads((Path(base) / "uv" / "uv.toml").read_text())
    except OSError, UnicodeDecodeError, tomllib.TOMLDecodeError:
        return "runs without a readable user uv configuration that sets the package-age limit"
    if not _is_at_least_a_week(settings.get(AGE_LIMIT)):
        return "runs without a package-age limit of at least a week in the user's uv configuration"
    if overrides := sorted((OVERRIDING_SETTINGS - {AGE_LIMIT}) & set(settings)):
        return f"runs with the user's uv setting {overrides[0]}, which adds a source the age limit does not cover"
    return next(
        (f"runs with the system uv configuration {path}" for path in _system_settings() if _overrides(path)), ""
    )


def _system_settings() -> list[Path]:
    """The system uv.toml files uv merges under the user's: each XDG_CONFIG_DIRS entry (default /etc/xdg), /etc."""
    configured = os.environ.get("XDG_CONFIG_DIRS") or DEFAULT_SYSTEM_CONFIG
    directories = [entry for entry in configured.split(os.pathsep) if entry]
    return [Path(directory) / "uv" / "uv.toml" for directory in [*directories, "/etc"]]


def _overrides(path: Path) -> bool:
    """Whether a system file sets a source or exception the age limit does not cover; one that cannot be read does."""
    try:
        settings = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return False
    except OSError, UnicodeDecodeError, tomllib.TOMLDecodeError:
        return True
    return not (OVERRIDING_SETTINGS - {AGE_LIMIT}).isdisjoint(settings)


def _program_reason(changes: list[shell_syntax.Command]) -> str:
    """A uv found in a directory the session writes could drop the limit before it runs the real one.

    git finds the worktree the project checks rely on, so it must be a system program too.
    """
    if not system_programs.is_system_program("git") or system_programs.inherits_git_location():
        return "runs where git, which finds the worktree, does not resolve to a root-owned system program"
    program = next(
        (item.arguments[0] for item in changes if not system_programs.is_system_program(item.arguments[0])), ""
    )
    return f"runs '{program}', which does not resolve to a root-owned system program" if program else ""


def _is_at_least_a_week(value: object) -> bool:
    """Whether an exclude-newer value refuses everything published in the last seven days.

    A span such as `1 week`, `7 days`, or `P7D` must be a week or longer; a date or timestamp must lie at
    least a week in the past. Any other value, or none, is not trusted.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if span := SPAN.fullmatch(text.casefold()):
        count, unit = int(span["count"] or span["iso_count"]), span["unit"] or span["iso_unit"]
        return count * (7 if unit.startswith("w") else 1) >= MINIMUM_AGE.days
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return False
    moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return moment <= datetime.now(UTC) - MINIMUM_AGE


def _has_overriding_settings(path: Path) -> bool:
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
    if any(isinstance(table, dict) and not OVERRIDING_SETTINGS.isdisjoint(table) for table in tables):
        return True
    return any(DIRECT_REFERENCE.search(entry) for entry in _dependency_entries(settings))


def _dependency_entries(settings: dict) -> list[str]:
    """Every requirement string in the project's dependencies, optional dependencies, and groups."""
    project = settings.get("project")
    project = project if isinstance(project, dict) else {}
    optional = project.get("optional-dependencies")
    groups = settings.get("dependency-groups")
    lists = [project.get("dependencies")]
    lists += list(optional.values()) if isinstance(optional, dict) else []
    lists += list(groups.values()) if isinstance(groups, dict) else []
    return [entry for entries in lists if isinstance(entries, list) for entry in entries if isinstance(entry, str)]


def _has_option_before_subcommand(item: shell_syntax.Command) -> bool:
    """A uv add or lock call with an option before its subcommand, such as `uv -q add` or `uv --directory x add`."""
    arguments = command_policy.canonical(item).arguments
    return (
        arguments[0] == PROGRAM
        and len(arguments) > 1
        and arguments[1].startswith("-")
        and not {"add", "lock"}.isdisjoint(arguments[2:])
    )


def _is_dependency_call(item: shell_syntax.Command) -> bool:
    """A uv add or lock call, whose options are always judged."""
    arguments = command_policy.canonical(item).arguments
    return arguments[0] == PROGRAM and len(arguments) > 1 and arguments[1] in {"add", "lock"}


def _changes_dependencies(item: shell_syntax.Command) -> bool:
    """Whether the call resolves anew: every `uv add`, and `uv lock` only when it upgrades (`-Uq`, `-Pruff`)."""
    arguments = command_policy.canonical(item).arguments
    return arguments[1] == "add" or any(_is_upgrade(word) for word in arguments[2:])


def _is_upgrade(word: str) -> bool:
    if word.startswith("--"):
        return word.partition("=")[0] in LOCK_UPGRADES
    return word.startswith("-") and not {"U", "P"}.isdisjoint(word[1:])


def _is_uv(item: shell_syntax.Command) -> bool:
    return not item.program_is_dynamic and item.arguments[0] == PROGRAM


def _is_companion(item: shell_syntax.Command) -> bool:
    name = Path(item.arguments[0]).name
    return not item.program_is_dynamic and item.arguments[0] == name and name in COMPANIONS


def _has_assignment(item: shell_syntax.Command) -> bool:
    return shell_inspection.has_prefix_assignment(item.raw, item.words[0])
