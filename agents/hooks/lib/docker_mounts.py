"""Find the host paths a docker run bind mounts and judge them against the secret-path policy.

Docker runs outside the sandbox, so a bind mount can expose files the sandbox denies. Compose files
are not read: only `-v`, `--volume`, and `--mount` on the command line count.
"""

import csv
from dataclasses import dataclass
import os
from pathlib import Path
import re

import secret_path_policy
import shell_paths
import shell_syntax


# Options that take the next word as their value, so that word is never the subcommand.
DOCKER_VALUED = frozenset({"-H", "--host", "-c", "--context", "--config", "-l", "--log-level"})
DOCKER_VALUED |= frozenset({"--tlscacert", "--tlscert", "--tlskey"})
COMPOSE_VALUED = frozenset({"-f", "--file", "-p", "--project-name", "--profile", "--env-file", "--project-directory"})
COMPOSE_VALUED |= frozenset({"--ansi", "--progress", "--parallel"})
# `-v` may follow boolean short flags in one cluster and take the rest of the word as its value.
SHORT_VOLUME = re.compile(r"-[itdPq]*v=?(.*)")
LONG_VOLUME = re.compile(r"--volume(?:=(.*))?")
LONG_MOUNT = re.compile(r"--mount(?:=(.*))?")
WORKING_DIRECTORY = re.compile(r"\$(?:PWD\b|\{PWD\})")
# Stands for a --mount value that is not valid CSV: its source cannot be known, so it asks.
RUN_TIME_SOURCE = "$(unreadable --mount value)"


@dataclass(frozen=True, slots=True)
class Exposure:
    """A bind mount source that reaches a protected path, or whose path is known only at run time."""

    path: str
    reason: str


def exposures(
    command: shell_syntax.Command, rules: list[dict], directories: tuple[Path | None, ...]
) -> list[Exposure]:
    """The secret exposures of one docker call in each directory it may run in; other calls have none."""
    sources = bind_sources(words_after_subcommand(command))
    found = (exposure(source, rules, base) for base in directories for source in sources)
    return list(dict.fromkeys(item for item in found if item is not None))


def words_after_subcommand(command: shell_syntax.Command) -> list[str]:
    """The words after `docker [container|compose] run|create`, or none for any other call."""
    if command.arguments[0] not in {"docker", "docker-compose"}:
        return []
    words = [unquoted(word, dynamic) for word, dynamic in zip(command.arguments, command.dynamic, strict=True)]
    if words[0] == "docker-compose":
        return called(after_options(words[1:], COMPOSE_VALUED), {"run"})
    rest = after_options(words[1:], DOCKER_VALUED)
    if rest[:1] == ["compose"]:
        return called(after_options(rest[1:], COMPOSE_VALUED), {"run"})
    if rest[:1] == ["container"]:
        rest = after_options(rest[1:], frozenset())
    return called(rest, {"run", "create"})


def called(words: list[str], subcommands: set[str]) -> list[str]:
    """The words after the subcommand when it is one of those named, else none."""
    return words[1:] if words[:1] and words[0] in subcommands else []


def after_options(words: list[str], valued: frozenset[str]) -> list[str]:
    """Drop the leading options and their values, leaving the subcommand first."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in valued else 1
    return words[index:]


def unquoted(word: str, dynamic: bool) -> str:
    """A run-time word carries its source text, so drop its quotes before reading it."""
    return "".join(shell_paths.unquoted_words(word)) if dynamic else word


def bind_sources(words: list[str]) -> list[str]:
    sources: list[str] = []
    for index, word in enumerate(words):
        following = words[index + 1] if index + 1 < len(words) else ""
        if match := SHORT_VOLUME.fullmatch(word) or LONG_VOLUME.fullmatch(word):
            sources += volume_source(match[1] or following)
        elif match := LONG_MOUNT.fullmatch(word):
            sources += mount_source(match[1] or following)
    return sources


def volume_source(value: str) -> list[str]:
    """`source:target[:options]` binds a host path; a bare container path is an anonymous volume."""
    return [value.partition(":")[0]] if ":" in value else []


def mount_source(value: str) -> list[str]:
    """Read the value as docker does: CSV fields, keys and type in any case, the last source key wins."""
    try:
        fields = next(csv.reader([value]), [])
    except csv.Error:
        return [RUN_TIME_SOURCE]
    pairs = [(key.strip().lower(), item) for key, _, item in (field.partition("=") for field in fields)]
    sources = [item for key, item in pairs if key in {"source", "src"}]
    if dict(pairs).get("type", "").lower() != "bind":
        return []
    return sources[-1:] or [""]


def exposure(source: str, rules: list[dict], base: Path | None) -> Exposure | None:
    """Judge one source relative to the directory the call runs in; a named volume has no exposure."""
    if base is not None:
        source = WORKING_DIRECTORY.sub(lambda _: str(base), source)
    source = shell_paths.HOME_VARIABLE.sub(lambda _: str(Path.home()), source)
    if "$" in source or "`" in source:
        return Exposure(source, "its source is known only at run time")
    if not is_host_path(source):
        return None
    expanded = os.path.expanduser(source)
    if base is None and not os.path.isabs(expanded):
        return Exposure(source, "the directory it is relative to is known only at run time")
    path = os.path.normpath(os.path.join(base or "/", expanded))
    if reason := protected_reason(path, rules):
        return Exposure(shown(path), reason)
    return None


def is_host_path(source: str) -> bool:
    return "/" in source or source in {".", "..", "~"}


def protected_reason(path: str, rules: list[dict]) -> str:
    """Why the path or something inside it is protected, or an empty string.

    Paths compare without regard to case, as on a case-insensitive file system.
    """
    home = str(Path.home())
    if path == home or home.startswith(path.rstrip("/") + "/"):
        return "the home directory holds credential files and directories."
    folded = fold_case(path)
    patterns = [{**rule, "pattern": rule["pattern"].lower()} for rule in rules]
    # A directory is judged as its own entries are, so `secrets` is read as `secrets/`.
    if rule := secret_path_policy.blocked_rule(folded, patterns) or secret_path_policy.blocked_rule(
        folded + "/", patterns
    ):
        return rule["reason"]
    inside = next((rule for rule in patterns if is_below(literal_prefix(rule["pattern"]), folded)), None)
    return f"it contains protected files. {inside['reason']}" if inside else ""


def fold_case(path: str) -> str:
    """Lowercase everything below the home directory, whose own spelling the policy normalizes by."""
    home = str(Path.home())
    if path.lower() == home.lower():
        return home
    if path.lower().startswith(home.lower() + "/"):
        return home + path[len(home) :].lower()
    return path.lower()


def literal_prefix(pattern: str) -> str:
    """The directory or file a home-relative pattern starts from, with `~` expanded; empty for any other pattern."""
    if not pattern.startswith("~/"):
        return ""
    fixed = re.split(r"[*?\[]", pattern, maxsplit=1)[0].rstrip("/")
    return os.path.expanduser(fixed)


def is_below(prefix: str, path: str) -> bool:
    return bool(prefix) and (prefix == path or prefix.startswith(path.rstrip("/") + "/"))


def shown(path: str) -> str:
    home = str(Path.home())
    return "~" if path == home else secret_path_policy.normalize(path)
