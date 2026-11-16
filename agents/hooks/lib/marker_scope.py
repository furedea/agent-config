"""Where each suppression marker in a text reaches: the text a change to which changes what it suppresses."""

import bisect
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Mark:
    """One marker: its line number, whether it sits in a node that decides it counts, and its scope's text."""

    line: int
    in_node: bool
    scope: str


@dataclass(frozen=True, slots=True)
class Layout:
    """Where the lines, deciding nodes and attribute brackets of a text start and end, for lookups by offset."""

    text: str
    line_starts: list[int]
    spans: list[tuple[int, int]]
    # By the `#` of each attribute, where its `]` sits; only for the attribute marker.
    closings: dict[int, int] | None

    @classmethod
    def of(cls, text: str, spans: list[tuple[int, int]], *, attribute: bool) -> Layout:
        """Index `text` once; for an attribute, a bracket in one of `spans` (a string or comment) does not count."""
        # The last entry starts a line past the text, so every line has an end.
        line_starts = [0, *(match.end() for match in re.finditer("\n", text)), len(text) + 1]
        spans = sorted(spans)
        return cls(text, line_starts, spans, _closing_brackets(text, spans) if attribute else None)

    def marks(self, starts: list[int]) -> list[Mark]:
        """The marker at each offset in `starts`, in order, with its scope's runs of space folded.

        A line break stays, since it ends a line comment: the words after it are code again.

        The scope runs from the marker to the end of its node, or else to the end of its attribute or line, so the
        rules it names on later lines count too.
        """
        node_ends = [self.node_end(start) for start in starts]
        following = _next_alike(starts, node_ends, len(self.text))
        return [
            Mark(
                self.line(start),
                node_end is not None,
                _folded(self.text[start : min(node_end or self.code_end(start), end)]),
            )
            for start, node_end, end in zip(starts, node_ends, following, strict=True)
        ]

    def line(self, position: int) -> int:
        """The number of the line that holds `position`."""
        return bisect.bisect_right(self.line_starts, position) - 1

    def node_end(self, position: int) -> int | None:
        """Where the node that holds `position` ends, or None outside every node."""
        return _span_end(self.spans, position)

    def code_end(self, position: int) -> int:
        """Past the `]` that closes an attribute, else the end of the text; any other marker's line end.

        An attribute without its `]` may reach any line below, so it takes up the rest of the text.
        """
        if self.closings is None:
            return self.line_starts[self.line(position) + 1] - 1
        closing = self.closings.get(position)
        return closing + 1 if closing is not None else self.line_starts[-1] - 1


def _next_alike(starts: list[int], node_ends: list[int | None], length: int) -> list[int]:
    """For each marker, where the next marker that is in a node exactly when it is starts, else the text's end.

    A scope stops there, since that marker takes up the text from there; the scopes of each kind then never overlap, so
    the work grows with the text alone. A marker of the other kind, such as one in a comment inside an attribute, takes
    up nothing of the scope around it.
    """
    following = {True: length, False: length}
    result: list[int] = []
    for start, node_end in zip(reversed(starts), reversed(node_ends), strict=True):
        result.append(following[node_end is not None])
        following[node_end is not None] = start
    return result[::-1]


def _folded(scope: str) -> str:
    """The scope with each run of spaces and tabs as one space and each run of line breaks as one, unindented."""
    return re.sub(r" ?\n[\n ]*", "\n", re.sub(r"[^\S\n]+", " ", scope)).strip()


def _span_end(spans: list[tuple[int, int]], position: int) -> int | None:
    index = bisect.bisect_right(spans, (position, float("inf"))) - 1
    return spans[index][1] if index >= 0 and position < spans[index][1] else None


def _closing_brackets(text: str, inert: list[tuple[int, int]]) -> dict[int, int]:
    """For the `#` or `#!` that opens each attribute, the offset of the `]` that closes it, outside `inert` spans."""
    pairs: list[tuple[int, int]] = []
    opened: list[int] = []
    for match in re.finditer(r"[\[\]]", text):
        if _span_end(inert, match.start()) is not None:
            continue
        if match.group() == "[":
            opened.append(match.start())
        elif opened:
            pairs.append((opened.pop(), match.start()))
    return {
        start - len(prefix): end
        for start, end in pairs
        for prefix in ("#!", "#")
        if text[start - len(prefix) : start] == prefix
    }
