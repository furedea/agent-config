"""Match the shared secret-path policy against parsed literal path candidates."""

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path


def load(path: Path) -> list[dict]:
    """Read the versioned rule list at its boundary; raise ValueError for a missing or malformed file."""
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("unsupported policy version")
        rules = data.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError("empty rules")
        if not all(
            isinstance(rule, dict)
            and all(isinstance(rule.get(key), str) and rule[key] for key in ("pattern", "reason"))
            for rule in rules
        ):
            raise ValueError("invalid path rule")
        return rules
    except (OSError, ValueError) as error:
        raise ValueError(f"secret path policy was not found or is invalid: {path}") from error


OTHER_USER_HOME = re.compile(r"^~[^/]+(?=/)")


def _normalize(value: str) -> str:
    """Name a path from the own home as `~/...`, and from another user's home as that user's `~/...`.

    The rules guard names such as `~/.aws/**`, which hold the same secrets in any user's home.
    """
    if value.startswith("$HOME/"):
        return "~/" + value[6:]
    if OTHER_USER_HOME.match(value):
        return OTHER_USER_HOME.sub("~", value)
    home = str(Path.home()) + "/"
    return "~/" + value[len(home) :] if value.startswith(home) else value


def _is_candidate(value: str) -> bool:
    return "/" in value or "." in value or value in {"id_rsa", "id_ed25519"}


def _applies(rule: dict, *, editing: bool) -> bool:
    """A write-only rule guards file edits; a command that merely names the path may only read it."""
    return editing or "read" in rule.get("access", ("read",))


def blocked_rule(value: str, rules: list[dict], *, editing: bool = False) -> dict | None:
    """The first rule whose pattern matches a word that looks like a path, or None.

    Pass `editing` when the path is the target of a file edit. Rules that name only `write` access are then
    enforced; for a path inside a command they are left to the sandbox, which sees what the command does.
    `$HOME/`, the home directory, and another user's `~name/` are matched as `~/`; symlinks are not resolved.
    """
    if not _is_candidate(value):
        return None
    path = _normalize(value)
    # Do not resolve symlinks: this policy concerns named paths, not a sandbox.
    for rule in (rule for rule in rules if _applies(rule, editing=editing)):
        pattern = rule["pattern"]
        if fnmatchcase(path, pattern) or (pattern.startswith("**/") and fnmatchcase(path, pattern[3:])):
            return rule
    return None
