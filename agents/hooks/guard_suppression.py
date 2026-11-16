#!/usr/bin/env -S python3 -IB
"""Hand any new lint or type-check suppression in code to the user.

The numeric AGENTS.md rules are enforced by lint, and a real exception gets a per-site suppression
with a reason. Whether an exception is real is the user's judgment, so an edit that adds a
suppression marker to a code file, or changes the rules or lints one names, asks; moving or deleting
one does not.
"""

import difflib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

import audit_log
import comment_nodes
import hook_decision
import hook_input
import marker_scope
import notebook_cells
import patch_input
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
    # ast-grep honors the word anywhere in a comment, even inside a longer word, so any mention asks; a false
    # positive only asks.
    "ast-grep-ignore": re.compile(r"ast-grep-ignore"),
}
# The lint hook also scans YAML and Nix, so a project's own ast-grep rules can be suppressed there.
MARKER_SUFFIXES = {"ast-grep-ignore": CODE_SUFFIXES | {".yml", ".yaml", ".nix"}}
# The part of a marker's scope that names what it suppresses; the rest, such as a reason, may change without asking.
# A marker without one here, or whose scope this does not match, is compared by its whole scope: ast-grep reads every
# word after its marker as a rule id.
DIRECTIVES = {
    "noqa": re.compile(r"#\s*(?:ruff:\s*)?noqa(?::\s*[A-Z]+[0-9]+(?:\s*,?\s*[A-Z]+[0-9]+)*)?"),
    "type: ignore": re.compile(r"#\s*type:\s*ignore(?:\[[^\]]*\])?"),
    "pyright: ignore": re.compile(r"#\s*pyright:\s*ignore(?:\[[^\]]*\])?"),
    "pylint: disable": re.compile(r"#\s*pylint:\s*disable\s*=\s*[\w-]+(?:\s*,\s*[\w-]+)*"),
    # ESLint and oxlint take the text after two or more dashes as the description.
    "lint-disable comment": re.compile(r"(?:oxlint|eslint)-disable.*?(?=\s-{2,}(?:\s|$)|$)"),
    "biome-ignore": re.compile(r"biome-ignore[^:]*"),
    "@ts-ignore": re.compile(r"@ts-(?:ignore|expect-error|nocheck)\b"),
    "shellcheck disable": re.compile(r"#\s*shellcheck(?:\s+[\w-]+=\S+)+"),
    "nolint": re.compile(r"//\s*nolint(?::\s*[\w.-]+(?:\s*,\s*[\w.-]+)*)?"),
}
# The reason of a Rust attribute, which names no lint.
ATTRIBUTE_REASON = re.compile(r'\breason\s*=\s*"(?:[^"\\]|\\.)*"')
# Shell suffixes, where a bare word on its own line may end a heredoc around a marker.
HEREDOC_SUFFIXES = frozenset({".sh", ".bash"})
# Every other marker is a comment directive, counted only inside a comment; a Rust attribute anywhere but a string
# or comment.
CODE_MARKERS = frozenset({"allow or expect attribute"})
# A line that may open or close a string or comment, which without a parser may change what a marker line is.
DELIMITER = re.compile(r"[\"'`]|/\*|\*/|<!--|--!?>|\[\[|\]\]|<<|[|>][-+]?\s*$")
# An ast-grep marker on the first line followed by a blank line suppresses its rules for the whole file.
FILE_SCOPE = "ast-grep-ignore for the whole file"
UNPLACED = "a suppression in a file the guard could not rebuild"
OUT_OF_TIME = "comments the guard could not parse in time"
MOVED_IN = "a suppression that takes effect where the file moves"
PATCH_FILE = re.compile(r"^\*\*\* (Add|Update) File: (.+)$")
PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$")


@dataclass(frozen=True, slots=True)
class _Change:
    """Text an edit adds to and removes from one file.

    `whole` means the two texts are the whole file after and before the edit. `unplaced` means the edit changes a
    file that holds a marker without the guard seeing the whole result, so the marker may come to count anywhere.
    `cell_suffix` is the suffix of a notebook cell's language, which decides the markers in place of the path's.
    """

    path: str
    added: str
    removed: str
    whole: bool = False
    unplaced: bool = False
    moved_in: bool = False
    cell_suffix: str = ""

    def suffix(self) -> str:
        """The lowercase suffix whose language decides which markers count and how its text parses."""
        return self.cell_suffix or Path(self.path).suffix.lower()


def decide(payload: dict) -> Verdict:
    """Ask when the edit adds a suppression marker to a code file or changes what one names, otherwise allow.

    Handles Write, Edit, MultiEdit and apply_patch payloads; non-code files are never inspected.
    """
    comment_nodes.start_budget()
    # The provider runs the tool in the payload's directory, so a relative path names a file there.
    with hook_input.payload_directory(payload):
        added = [f"{name} in {change.path}" for change in _changes(payload) for name in _new_markers(change)]
    # A scan cut short leaves the comments unknown, and the fallback without them cannot see every new scope.
    if comment_nodes.budget_ran_out():
        added.append(OUT_OF_TIME)
    if not added:
        return hook_decision.ALLOW
    listed = ", ".join(added)
    return hook_decision.ask(
        f"Needs review: this edit adds a lint or type-check suppression ({listed}). "
        "Only the user decides whether an exception is warranted; state the reason.",
        "suppression",
    )


def _new_markers(change: _Change) -> list[str]:
    suffix = change.suffix()
    found = [
        name
        for name, pattern in MARKERS.items()
        if suffix in MARKER_SUFFIXES.get(name, CODE_SUFFIXES) and _has_new_scope(name, pattern, change)
    ]
    if suffix in MARKER_SUFFIXES["ast-grep-ignore"] and _widens_file_scope(change):
        found.append(FILE_SCOPE)
    if change.unplaced:
        found.append(UNPLACED)
    if change.moved_in:
        found.append(MOVED_IN)
    return found


def _widens_file_scope(change: _Change) -> bool:
    """Whether the edit may give a first-line ast-grep marker the whole file, or change the one that has it."""
    suffix = change.suffix()
    after = _file_marker(change.added, suffix) if change.whole else None
    return after is not None and after != _file_marker(change.removed, suffix)


def _file_marker(text: str, suffix: str) -> str | None:
    """The first line when it holds an ast-grep marker in a comment above a blank line.

    This counts the marker as the line-level check does; without the scanner, any marker on that line counts.
    """
    # A final newline ends the last line; it does not start an empty one.
    lines = _lines(text.removesuffix("\n"))
    if len(lines) < 2 or lines[1].strip() or not MARKERS["ast-grep-ignore"].search(lines[0]):
        return None
    marks = _marked_lines("ast-grep-ignore", text, suffix)
    if marks is not None and not any(in_comment for in_comment, _ in marks.get(0, ())):
        return None
    return lines[0].strip()


def _lines(text: str) -> list[str]:
    """Split at newlines only, as the scanner does; `str.splitlines` also splits at separators code keeps on a line."""
    return [line.removesuffix("\r") for line in text.split("\n")]


def _has_new_scope(name: str, pattern: re.Pattern[str], change: _Change) -> bool:
    """Whether a marker that counts (in a comment, or for a Rust attribute in code) has a scope the edit did not have.

    A marker is compared by the text of its scope, so naming other or fewer rules asks like a new marker. Without the
    scanner, comments cannot be told from strings: a marker line whose text is new asks, and so does a change to a
    line that may open or close a string or comment in text that holds a marker.
    """
    suffix = change.suffix()
    added, removed = (_marked_lines(name, text, suffix) for text in (change.added, change.removed))
    if added is None or removed is None:
        return _may_add_unparsed(pattern, change)
    # A fragment lacks the context that decides what is a comment or string in the file, so every mark of it counts.
    every_mark = not change.whole
    added_marks, removed_marks = (
        Counter(mark for marks in found.values() for mark in marks if every_mark or _counts(name, mark[0]))
        for found in (added, removed)
    )
    return bool(added_marks - removed_marks)


def _counts(name: str, in_node: bool) -> bool:
    """A comment directive counts inside a comment node; the attribute marker counts outside the inert nodes."""
    return in_node != (name in CODE_MARKERS)


def _may_add_unparsed(pattern: re.Pattern[str], change: _Change) -> bool:
    if Counter(_marker_lines(pattern, change.added)) - Counter(_marker_lines(pattern, change.removed)):
        return True
    if not pattern.search(change.added):
        return False
    before, after = _lines(change.removed), _lines(change.added)
    opcodes = difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
    changed = [line for tag, i1, i2, j1, j2 in opcodes if tag != "equal" for line in (*before[i1:i2], *after[j1:j2])]
    if change.suffix() in HEREDOC_SUFFIXES and "<<" in change.added + change.removed:
        return bool(changed)
    return any(DELIMITER.search(line) for line in changed)


def _marked_lines(name: str, text: str, suffix: str) -> dict[int, tuple[tuple[bool, str], ...]] | None:
    """By line number, each marker on the line as whether it is in a node that decides it counts, and its scope.

    The nodes are the inert strings and comments for the attribute marker, and the comments for every other marker;
    the language's parser finds them, so a block comment, raw string or block scalar around the line counts. The scope
    is the text from the marker to the end of its node, or else to the end of its attribute or line, with runs of
    space folded, so the rules it names on later lines count too. None means the nodes cannot be known.
    """
    starts = [match.start() for match in MARKERS[name].finditer(text)]
    if not starts:
        return {}
    find = comment_nodes.inert_spans if name in CODE_MARKERS else comment_nodes.comment_spans
    spans = find(text, suffix)
    if spans is None:
        return None
    marked: dict[int, list[tuple[bool, str]]] = {}
    for mark in marker_scope.Layout.of(text, spans, attribute=name in CODE_MARKERS).marks(starts):
        marked.setdefault(mark.line, []).append((mark.in_node, _directive(name, mark.scope)))
    return {number: tuple(marks) for number, marks in marked.items()}


def _directive(name: str, scope: str) -> str:
    """What of a marker's scope names what it suppresses."""
    if name in CODE_MARKERS:
        return ATTRIBUTE_REASON.sub("reason", scope)
    pattern = DIRECTIVES.get(name)
    match = pattern.match(scope) if pattern is not None else None
    return match.group() if match is not None else scope


def _marker_lines(pattern: re.Pattern[str], text: str) -> list[str]:
    """The marker lines with their indentation, which in YAML or a block may decide whether the line is a comment."""
    return [line.rstrip() for line in _lines(text) if pattern.search(line)]


def _changes(payload: dict) -> list[_Change]:
    tool = payload.get("tool_name") or ""
    values = payload.get("tool_input") or {}
    if tool == "apply_patch" or "patch" in values:
        return _patch_changes(hook_input.patch_body(values, tool or None))
    path = hook_input.file_path(values)
    if tool == "NotebookEdit":
        return _cell_changes(path, values)
    written = _field(values, "content", "file_text")
    if tool == "Write" or written:
        return [_Change(path, written, _existing_text(path), whole=True)]
    if values.get("command") == "insert":
        return [_change_after_insert(path, values)]
    edits = values.get("edits") or [] if tool == "MultiEdit" else [values]
    return [_edit_change(path, edits)]


def _cell_changes(path: str, values: dict) -> list[_Change]:
    edit = notebook_cells.code_cell_edit(path, values)
    if edit is None:
        return []
    return [_Change(path, edit.after, edit.before, whole=True, cell_suffix=edit.suffix)]


def _change_after_insert(path: str, values: dict) -> _Change:
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

    When a replacement does not apply to the file, the bare fragments are compared instead, and a marker in the file
    may come to count anywhere.
    """
    before = _existing_text(path)
    after = before
    pairs = [(_field(edit, "old_string", "old_str"), _field(edit, "new_string", "new_str")) for edit in edits]
    for edit, (old, new) in zip(edits, pairs, strict=True):
        if not old or old not in after:
            added, removed = "\n".join(new for _, new in pairs), "\n".join(old for old, _ in pairs)
            return _Change(path, added, removed, unplaced=_holds_marker(before, Path(path).suffix.lower()))
        after = after.replace(old, new) if edit.get("replace_all") else after.replace(old, new, 1)
    return _Change(path, after, before, whole=True)


def _field(values: dict, *names: str) -> str:
    """The first non-empty text among the names different editor tools give the same field."""
    return next((value for name in names if isinstance(value := values.get(name), str) and value), "")


def _patch_changes(patch: str) -> list[_Change]:
    """Judge each file of an apply_patch body whole after its hunks, or by its added and removed lines.

    A moved file is judged at its destination too, where markers the source's file type did not honor take effect.
    """
    files = _PatchFiles()
    current: _Hunks | None = None
    for line in _lines(patch):
        if current is not None and current.holds(line):
            current.lines.append(line)
            continue
        # The applier reads a header with the spaces around it trimmed.
        header = line.strip()
        if match := PATCH_FILE.match(header):
            current = files.start(match.group(2).strip(), added=match.group(1) == "Add")
        elif current is not None and (move := PATCH_MOVE.match(header)):
            files.move(current, move.group(1).strip())
        elif header.startswith("***") and header != patch_input.END_OF_FILE:
            current = None
        elif current is not None:
            current.lines.append(line)
    return [change for path, file_hunks in files.sections.items() for change in file_hunks.changes(path)]


@dataclass(slots=True)
class _PatchFiles:
    """The file sections of a patch, keyed by the path each names.

    A file reached twice, as a section or a move destination under any spelling, is applied in an order this does
    not model, so its sections are marked repeated and fail closed.
    """

    sections: dict[str, _Hunks] = field(default_factory=dict)
    owners: dict[str, _Hunks] = field(default_factory=dict)

    def start(self, path: str, *, added: bool) -> _Hunks:
        """Begin the section of a file, or mark the section that already reaches it as repeated."""
        owner = self.owners.get(_identity(path))
        if owner is not None:
            owner.repeated = True
            return owner
        self.sections[path] = self.owners[_identity(path)] = _Hunks(added=added)
        return self.sections[path]

    def move(self, hunks: _Hunks, destination: str) -> None:
        """Record where a section's file moves, marking both sections when another already reaches it."""
        hunks.destination = destination
        owner = self.owners.setdefault(_identity(destination), hunks)
        if owner is not hunks:
            owner.repeated = hunks.repeated = True


def _identity(path: str) -> str:
    """The real path, case-folded, since a file system may ignore case; a false match only fails closed."""
    return os.path.realpath(path).casefold()


@dataclass(slots=True)
class _Hunks:
    """The hunk lines of one file in a patch and where the file moves to."""

    added: bool = False
    lines: list[str] = field(default_factory=list)
    destination: str = ""
    repeated: bool = False

    def holds(self, line: str) -> bool:
        """Whether the applier reads `line` as part of this section rather than as a header.

        An added file takes only `+` lines; an updated one takes any line that does not itself start with `***`, so a
        context line such as ` *** Notes` stays in the section.
        """
        return line.startswith("+") if self.added else not line.startswith("***")

    def changes(self, path: str) -> list[_Change]:
        existing = _existing_text(path)
        source = self._source(path, existing)
        if not self.destination:
            return [source]
        # A carried marker counts by itself; cut out of the file, its line could parse differently.
        # Judge what arrives: the patched text when the guard could rebuild it, else the file as it stands.
        moved = source.added if source.whole else existing
        moved_in = bool(_newly_honored(moved, Path(path).suffix.lower(), Path(self.destination).suffix.lower()))
        # Only the destination exists after the move, so only its suffix decides which markers count.
        return [_Change(self.destination, source.added, source.removed, source.whole, source.unplaced, moved_in)]

    def _source(self, path: str, existing: str) -> _Change:
        """The whole file before and after when every hunk matches it exactly, else the changed lines.

        The applier also matches context loosely (whitespace, Unicode punctuation), so where an inexact hunk lands is
        unknown; in a file that holds a marker, that fails closed.
        """
        if self.repeated:
            return _Change(path, "", "", unplaced=True)
        if self.added:
            return _Change(
                path, "".join(f"{line[1:]}\n" for line in self.lines if line.startswith("+")), existing, True
            )
        after = patch_input.patched_text(existing, self.lines)
        if after is not None:
            return _Change(path, after, existing, whole=True)
        added = "\n".join(line[1:] for line in self.lines if line.startswith("+"))
        removed = "\n".join(line[1:] for line in self.lines if line.startswith("-"))
        return _Change(path, added, removed, unplaced=_holds_marker(existing, Path(path).suffix.lower()))


def _newly_honored(text: str, source: str, destination: str) -> str:
    """The lines of a moved file whose markers may take effect only at the destination.

    These are markers the source suffix did not honor, and ast-grep markers that only the destination's comment syntax
    reads as a comment, such as a Go line starting with `#` that becomes a Python comment.
    """
    honored = [
        pattern
        for name, pattern in MARKERS.items()
        if destination in (suffixes := MARKER_SUFFIXES.get(name, CODE_SUFFIXES)) and source not in suffixes
    ]
    lines = _lines(text)
    carried = {number for number, line in enumerate(lines) if any(pattern.search(line) for pattern in honored)}
    return "\n".join(lines[number] for number in sorted(carried | _becomes_comment(text, source, destination)))


def _becomes_comment(text: str, source: str, destination: str) -> set[int]:
    """Lines with a comment marker that is in a comment at the destination which the source did not read so."""
    if source == destination:
        return set()
    lines: set[int] = set()
    for name, pattern in MARKERS.items():
        if destination not in MARKER_SUFFIXES.get(name, CODE_SUFFIXES):
            continue
        before, after = (_marked_lines(name, text, suffix) for suffix in (source, destination))
        if before is None or after is None:
            lines |= {number for number, line in enumerate(_lines(text)) if pattern.search(line)}
            continue
        lines |= {
            number
            for number, marks in after.items()
            if any(_counts(name, in_node) for in_node, _ in marks) and marks != before.get(number)
        }
    return lines


def _holds_marker(text: str, suffix: str) -> bool:
    """Whether the file holds any marker its suffix honors."""
    return any(
        pattern.search(text) for name, pattern in MARKERS.items() if suffix in MARKER_SUFFIXES.get(name, CODE_SUFFIXES)
    )


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
