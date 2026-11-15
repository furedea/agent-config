"""Decode apply_patch headers and inserted text without executing the patch."""

import re
from dataclasses import dataclass, field

END_OF_FILE = "*** End of File"


def is_patch(text: str) -> bool:
    """Recognize patch format independently of which input field carried it."""
    return bool(
        re.search(r"^\*\*\* (?:Begin Patch|End Patch|(?:Add|Update|Delete) File:|Move to:)", text, re.MULTILINE)
    )


def paths(patch: str) -> tuple[str, ...]:
    """The distinct files a patch adds, updates, deletes, or moves to, sorted."""
    return tuple(
        sorted(set(re.findall(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", patch, re.MULTILINE)))
    )


def added_text(patch: str) -> str:
    """The inserted lines of a patch joined by newlines, without their `+` marker or the `+++` header."""
    return "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))


@dataclass(slots=True)
class _Chunk:
    """One `@@` section of an update hunk: its anchor line, the lines it expects, and the lines it leaves."""

    anchor: str = ""
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)

    def landing(self, lines: list[str], cursor: int) -> int | None:
        """Where the expected lines start, after the anchor line when there is one; a pure addition appends."""
        if self.anchor:
            found = _find(lines, [self.anchor], cursor)
            if found is None:
                return None
            cursor = found + 1
        if not self.old:
            return len(lines)
        found = _find(lines, self.old, cursor)
        # A second exact match leaves where the applier lands to its anchor rules, so the place is unknown.
        return found if found is None or _find(lines, self.old, found + 1) is None else None


def patched_text(existing: str, hunks: list[str]) -> str | None:
    """The file after an update patch's hunk lines, or None when a hunk does not match the file exactly.

    The applier tries an exact match before any loose one, so a hunk that matches exactly lands where this puts it.
    """
    lines = existing.split("\n")
    final_newline = len(lines) > 1 and lines[-1] == ""
    lines = lines[:-1] if final_newline or lines == [""] else lines
    chunks = _chunks(hunks)
    if chunks is None:
        return None
    cursor = 0
    for chunk in chunks:
        start = chunk.landing(lines, cursor)
        if start is None:
            return None
        lines[start : start + len(chunk.old)] = chunk.new
        cursor = start + len(chunk.new)
    return "\n".join(lines) + ("\n" if final_newline or not existing else "")


def _chunks(hunks: list[str]) -> list[_Chunk] | None:
    """The chunks of the hunk lines, or None for a line this does not place as the applier would.

    An empty line is an empty context line. An end-of-file chunk is matched from the end, which this does not do.
    """
    chunks: list[_Chunk] = []
    for raw in hunks:
        line = raw or " "
        if line.startswith("@@") or not chunks:
            chunks.append(_Chunk(line[2:].strip() if line.startswith("@@") else ""))
        if line[:1] not in {" ", "-", "+", "@"}:
            return None
        if line[:1] in {" ", "-"}:
            chunks[-1].old.append(line[1:])
        if line[:1] in {" ", "+"}:
            chunks[-1].new.append(line[1:])
    return chunks


def _find(lines: list[str], wanted: list[str], start: int) -> int | None:
    return next(
        (
            index
            for index in range(start, len(lines) - len(wanted) + 1)
            if lines[index : index + len(wanted)] == wanted
        ),
        None,
    )
