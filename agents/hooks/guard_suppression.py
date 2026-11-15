#!/usr/bin/env -S python3 -IB
"""Hand any new lint or type-check suppression in code to the user.

The numeric AGENTS.md rules are enforced by lint, and a real exception gets a per-site suppression
with a reason. Whether an exception is real is the user's judgment, so an edit that adds more
suppression markers to a code file than it removes asks; moving or deleting one does not. An ast-grep
marker is compared by its text, so changing the rules it names asks too.
"""

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

import audit_log
import hook_decision
import hook_input
from hook_decision import Verdict

RULE = "guard_suppression.sh"
CODE_SUFFIXES = frozenset(
    {".py", ".pyi", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go", ".sh", ".bash", ".lua"}
)
MARKERS = {
    "noqa": re.compile(r"#\s*(?:ruff:\s*)?noqa\b"),
    "type: ignore": re.compile(r"#\s*type:\s*ignore\b"),
    "pyright: ignore": re.compile(r"#\s*pyright:\s*ignore\b"),
    "pylint: disable": re.compile(r"#\s*pylint:\s*disable\b"),
    "lint-disable comment": re.compile(r"\b(?:oxlint|eslint)-disable\b"),
    "biome-ignore": re.compile(r"\bbiome-ignore\b"),
    "@ts-ignore": re.compile(r"@ts-(?:ignore|expect-error|nocheck)\b"),
    "allow or expect attribute": re.compile(r"#!?\[\s*(?:allow|expect)\s*\("),
    "shellcheck disable": re.compile(r"#\s*shellcheck\s+disable="),
    "nolint": re.compile(r"//\s*nolint\b"),
    # ast-grep honors the word anywhere in a comment, so any mention asks; a false positive only asks.
    "ast-grep-ignore": re.compile(r"\bast-grep-ignore\b"),
}
# The lint hook also scans YAML and Nix, so a project's own ast-grep rules can be suppressed there.
MARKER_SUFFIXES = {"ast-grep-ignore": CODE_SUFFIXES | {".yml", ".yaml", ".nix"}}
# An ast-grep marker that names no rule suppresses every rule, and the word only counts in a comment, so a marker is
# compared by its comment's text: changing the named rules, or turning a string that holds the word into a comment,
# asks.
COMPARED_BY_TEXT = frozenset({"ast-grep-ignore"})
COMMENT_OPENERS = {".rs": ("//", "/*"), ".lua": ("--",), ".nix": ("#", "/*")}
SLASH_COMMENT_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".go"})
QUOTES = frozenset("'\"`")
# An ast-grep marker on the first line followed by a blank line suppresses its rules for the whole file.
FILE_SCOPE = "ast-grep-ignore for the whole file"
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$")
PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$")


@dataclass(frozen=True, slots=True)
class _Change:
    """Text an edit adds to and removes from one file.

    `whole` means the two texts are the whole file after and before the edit. `rescopes` means the edit changes a
    file that holds an ast-grep marker without the guard seeing the whole result, so the marker may come to cover
    the whole file.
    """

    path: str
    added: str
    removed: str
    whole: bool = False
    rescopes: bool = False


def decide(payload: dict) -> Verdict:
    """Ask when the edit adds more suppression markers to a code file than it removes, otherwise allow.

    Handles Write, Edit, MultiEdit and apply_patch payloads; non-code files are never inspected.
    """
    added = [(change.path, name) for change in _changes(payload) for name in _new_markers(change)]
    if not added:
        return hook_decision.ALLOW
    listed = ", ".join(f"{name} in {path}" for path, name in added)
    return hook_decision.ask(
        f"Needs review: this edit adds a lint or type-check suppression ({listed}). "
        "Only the user decides whether an exception is warranted; state the reason.",
        "suppression",
    )


def _new_markers(change: _Change) -> list[str]:
    suffix = Path(change.path).suffix
    found = [
        name
        for name, pattern in MARKERS.items()
        if suffix in MARKER_SUFFIXES.get(name, CODE_SUFFIXES) and _adds(name, pattern, change)
    ]
    if suffix in MARKER_SUFFIXES["ast-grep-ignore"] and _widens_file_scope(change):
        found.append(FILE_SCOPE)
    return found


def _widens_file_scope(change: _Change) -> bool:
    """Whether the edit may give a first-line ast-grep marker the whole file, or change the one that has it."""
    if change.rescopes:
        return True
    after = _file_marker(change.added) if change.whole else None
    return after is not None and after != _file_marker(change.removed)


def _file_marker(text: str) -> str | None:
    # A final newline ends the last line; it does not start an empty one.
    lines = _lines(text.removesuffix("\n"))
    if len(lines) < 2 or lines[1].strip() or not MARKERS["ast-grep-ignore"].search(lines[0]):
        return None
    return lines[0].strip()


def _lines(text: str) -> list[str]:
    """Split at newlines only, as the scanner does; `str.splitlines` also splits at separators code keeps on a line."""
    return [line.removesuffix("\r") for line in text.split("\n")]


def _adds(name: str, pattern: re.Pattern[str], change: _Change) -> bool:
    """Count markers, or for markers compared by text, find a marker whose text is new."""
    if name not in COMPARED_BY_TEXT:
        return len(pattern.findall(change.added)) > len(pattern.findall(change.removed))
    openers = _comment_openers(Path(change.path).suffix)
    added, removed = (_marked_text(pattern, text, openers) for text in (change.added, change.removed))
    return bool(Counter(added) - Counter(removed))


def _marked_text(pattern: re.Pattern[str], text: str, openers: tuple[str, ...]) -> list[str]:
    """Each marker's comment from its opener on, or the whole line when the marker is not inside a comment."""
    marked = []
    for line in _lines(text):
        if match := pattern.search(line):
            start = _comment_start(line, openers)
            marked.append(line[start:].strip() if start is not None and start <= match.start() else line.strip())
    return marked


def _comment_openers(suffix: str) -> tuple[str, ...]:
    if suffix in COMMENT_OPENERS:
        return COMMENT_OPENERS[suffix]
    return ("//", "/*") if suffix in SLASH_COMMENT_SUFFIXES else ("#",)


def _comment_start(line: str, openers: tuple[str, ...]) -> int | None:
    """Where the first comment outside a quoted string starts; a quote the guard misreads only makes it ask."""
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if quote:
            quote = "" if char == quote and not escaped else quote
            escaped = not escaped and char == "\\"
        elif char in QUOTES:
            quote = char
        elif line.startswith(openers, index):
            return index
    return None


def _changes(payload: dict) -> list[_Change]:
    tool = payload.get("tool_name") or ""
    values = payload.get("tool_input") or {}
    if tool == "apply_patch" or "patch" in values:
        return _patch_changes(hook_input.patch_body(values, tool or None))
    path = hook_input.file_path(values)
    written = _field(values, "content", "file_text")
    if tool == "Write" or written:
        return [_Change(path, written, _existing_text(path), whole=True)]
    if values.get("command") == "insert":
        return [_insert_change(path, values)]
    edits = values.get("edits") or [] if tool == "MultiEdit" else [values]
    return [_edit_change(path, edits)]


def _insert_change(path: str, values: dict) -> _Change:
    """An editor `insert` puts `new_str` after line `insert_line` (0 for the top); judge the whole file after it."""
    before = _existing_text(path)
    line = values.get("insert_line")
    new = _field(values, "new_str", "new_string")
    if not isinstance(line, int) or isinstance(line, bool) or line < 0:
        return _Change(path, new, "")
    lines = before.split("\n")
    after = "\n".join([*lines[:line], *new.split("\n"), *lines[line:]])
    return _Change(path, after, before, whole=True)


def _edit_change(path: str, edits: list[dict]) -> _Change:
    """Apply the replacements to the file in order and compare the whole text, so no partial edit is missed.

    When a replacement does not apply to the file, the bare fragments are compared instead, and an ast-grep marker
    in the file may come to cover all of it.
    """
    before = _existing_text(path)
    after = before
    pairs = [(_field(edit, "old_string", "old_str"), _field(edit, "new_string", "new_str")) for edit in edits]
    for edit, (old, new) in zip(edits, pairs, strict=True):
        if not old or old not in after:
            added, removed = "\n".join(new for _, new in pairs), "\n".join(old for old, _ in pairs)
            return _Change(path, added, removed, rescopes=_holds_ast_grep_marker(before))
        after = after.replace(old, new) if edit.get("replace_all") else after.replace(old, new, 1)
    return _Change(path, after, before, whole=True)


def _field(values: dict, *names: str) -> str:
    """The first non-empty text among the names different editor tools give the same field."""
    return next((value for name in names if isinstance(value := values.get(name), str) and value), "")


def _patch_changes(patch: str) -> list[_Change]:
    """Split an apply_patch body into per-file added and removed text.

    A moved file is judged at its destination too, where markers the source's file type did not honor take effect.
    """
    hunks: dict[str, _Hunks] = {}
    current: _Hunks | None = None
    for line in _lines(patch):
        if match := PATCH_FILE.match(line):
            current = hunks.setdefault(match.group(1).strip(), _Hunks())
        elif current is not None and (move := PATCH_MOVE.match(line)):
            current.destination = move.group(1).strip()
        elif current is not None and line[:1] in {"+", "-", " "}:
            current.lines.append(line)
    return [change for path, file_hunks in hunks.items() for change in file_hunks.changes(path)]


@dataclass(slots=True)
class _Hunks:
    """The hunk lines of one file in a patch and where the file moves to."""

    lines: list[str] = field(default_factory=list)
    destination: str = ""

    def changes(self, path: str) -> list[_Change]:
        added = "\n".join(line[1:] for line in self.lines if line.startswith("+"))
        removed = "\n".join(line[1:] for line in self.lines if line.startswith("-"))
        existing = _existing_text(path)
        # The applier matches context loosely (whitespace, Unicode punctuation), so where a hunk lands is unknown.
        source = _Change(path, added, removed, rescopes=bool(self.lines) and _holds_ast_grep_marker(existing))
        if not self.destination:
            return [source]
        carried = _newly_honored(existing, Path(path).suffix, Path(self.destination).suffix)
        return [source, _Change(self.destination, f"{carried}\n{added}", removed, rescopes=source.rescopes)]


def _newly_honored(text: str, source: str, destination: str) -> str:
    """The lines of a moved file with a marker that the destination suffix honors and the source suffix did not."""
    honored = [
        pattern
        for name, pattern in MARKERS.items()
        if destination in (suffixes := MARKER_SUFFIXES.get(name, CODE_SUFFIXES)) and source not in suffixes
    ]
    return "\n".join(line for line in _lines(text) if any(pattern.search(line) for pattern in honored))


def _holds_ast_grep_marker(text: str) -> bool:
    """Whether a marker that an edit could move to the top, above a blank line, is in the file."""
    return MARKERS["ast-grep-ignore"].search(text) is not None


def _existing_text(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def main() -> int:
    """Run the hook on a JSON payload from stdin and return the process exit status.

    Returns 2 when stdin is not JSON. An asking verdict is recorded in the audit log before it is emitted.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError, OSError:
        print("BLOCKED: failed to parse tool input JSON", file=sys.stderr)
        return 2
    verdict = decide(payload)
    if verdict.decision != "allow":
        audit_log.escalated(
            audit_log.Refusal(
                payload.get("tool_name") or "Edit",
                RULE,
                payload.get("session_id", ""),
                payload=payload,
                detail=verdict.detail,
            )
        )
    return hook_decision.emit(verdict)


if __name__ == "__main__":
    sys.exit(main())
