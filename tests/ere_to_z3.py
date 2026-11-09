"""Convert the POSIX extended regular expressions of the command rules into Z3 regular expressions.

The converter covers the dialect the rules use and refuses anything else, so a new construct fails
loudly instead of being read wrongly. `^` and `$` become sentinel characters around the text, which
lets one regular expression say "the pattern occurs somewhere in the line", as `grep -E` does.

The converter models grep in the C locale. Constructs whose meaning the locale changes are refused (the
letter classes, the case folding of a non-ASCII letter); `[[:space:]]` is the exception, read as ASCII white
space because the rules use it throughout. Under a UTF-8 locale it also admits Unicode spaces such as U+2003,
which this audit does not see.
"""

from dataclasses import dataclass, field
import re

import z3


MAX_CODE_POINT = 0x2FFFF
# The two highest code points are reserved as the line's sentinels; Unicode noncharacters never occur in a command.
START = chr(MAX_CODE_POINT - 1)
END = chr(MAX_CODE_POINT)
# Line breaks are folded to spaces before grep runs, and a shell argument cannot hold NUL.
TEXT_CHARACTERS = ((1, 9), (11, 12), (14, MAX_CODE_POINT - 2))
# Only the classes whose members do not depend on the locale are modeled. `space` is read as the ASCII
# white space, which is what the guard's text holds; the letter classes grow with a UTF-8 locale, so they
# are refused rather than modeled as ASCII-only.
POSIX_CLASSES = {
    "space": ((9, 13), (32, 32)),
    "digit": ((48, 57),),
}
# Escapes that are anchors in GNU grep (`\<` `\>` `\`` `\'`) and in BSD grep, so never a plain character.
ANCHOR_ESCAPES = frozenset("<>`'")
CASE_OFFSET = 32
UPPERCASE = (65, 90)
LOWERCASE = (97, 122)

Intervals = tuple[tuple[int, int], ...]


class UnsupportedPattern(ValueError):
    """The pattern uses syntax outside the dialect the command rules are written in."""


def matches(pattern: str, text: str, ignore_case: bool = False) -> bool:
    """Whether the pattern occurs in the text, decided by Z3 on the converted pattern."""
    wrapped = z3.StringVal(START + text + END)
    return z3.is_true(z3.simplify(z3.InRe(wrapped, search_language(pattern, ignore_case))))


def search_language(pattern: str, ignore_case: bool = False) -> z3.ReRef:
    """The regular expression over `START + line + END` that holds when the pattern occurs in the line."""
    anywhere = z3.Star(any_character())
    return z3.Concat(anywhere, pattern_language(pattern, ignore_case), anywhere)


def pattern_language(pattern: str, ignore_case: bool = False) -> z3.ReRef:
    """The regular expression for the pattern alone, over text that may carry the sentinels."""
    return Parser(pattern, ignore_case).parse()


def any_character() -> z3.ReRef:
    """Any character at all, the sentinels included."""
    return characters(((1, MAX_CODE_POINT),))


def witness(pattern: str, ignore_case: bool = False) -> str | None:
    """A line the pattern occurs in, or None when no line holds it."""
    return find_line(search_language(pattern, ignore_case))


def find_line(language: z3.ReRef, timeout_ms: int = 30_000) -> str | None:
    """A line whose `START + line + END` is in the language, or None when there is none."""
    line = z3.String("line")
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(z3.InRe(z3.Concat(z3.StringVal(START), line, z3.StringVal(END)), language))
    solver.add(z3.InRe(line, z3.Star(characters(TEXT_CHARACTERS))))
    outcome = solver.check()
    if outcome == z3.unknown:
        raise TimeoutError("Z3 could not decide the language within the time limit")
    if outcome == z3.unsat:
        return None
    value = solver.model()[line]
    return decode(value.as_string()) if value is not None else ""


def decode(escaped: str) -> str:
    """Z3 writes every non-printable or non-ASCII character, and the backslash, as \\u{hex}."""
    return re.sub(r"\\u\{([0-9a-fA-F]+)\}", lambda found: chr(int(found.group(1), 16)), escaped)


def characters(intervals: Intervals) -> z3.ReRef:
    ranges = [z3.Range(chr(low), chr(high)) for low, high in intervals]
    if not ranges:
        return z3.Empty(z3.ReSort(z3.StringSort()))
    return ranges[0] if len(ranges) == 1 else z3.Union(*ranges)


def normalize(intervals: Intervals) -> Intervals:
    merged: list[tuple[int, int]] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return tuple(merged)


def intersect(first: Intervals, second: Intervals) -> Intervals:
    pairs = [(max(a, c), min(b, d)) for a, b in first for c, d in second]
    return normalize(tuple(pair for pair in pairs if pair[0] <= pair[1]))


def complement_in_text(intervals: Intervals) -> Intervals:
    """The text characters outside the set."""
    chosen = normalize(intervals)
    return tuple(gap for low, high in TEXT_CHARACTERS for gap in gaps(low, high, intersect(((low, high),), chosen)))


def gaps(low: int, high: int, taken: Intervals) -> list[tuple[int, int]]:
    """What remains of low..high around the sorted, disjoint taken intervals."""
    remaining: list[tuple[int, int]] = []
    start = low
    for taken_low, taken_high in taken:
        if taken_low > start:
            remaining.append((start, taken_low - 1))
        start = taken_high + 1
    if start <= high:
        remaining.append((start, high))
    return remaining


def is_cased_non_ascii(code: int) -> bool:
    character = chr(code)
    return code > 127 and (character.lower() != character or character.upper() != character)


def fold_case(intervals: Intervals) -> Intervals:
    """The set with the ASCII letters' other case added; a cased non-ASCII character is refused, as its
    folding depends on the locale grep runs in."""
    if any(is_cased_non_ascii(code) for low, high in intervals for code in range(low, high + 1)):
        raise UnsupportedPattern(
            "a cased non-ASCII character cannot be case folded: the locale decides its other case"
        )
    shifted = [(low + CASE_OFFSET, high + CASE_OFFSET) for low, high in intersect(intervals, (UPPERCASE,))]
    shifted += [(low - CASE_OFFSET, high - CASE_OFFSET) for low, high in intersect(intervals, (LOWERCASE,))]
    return normalize(intervals + tuple(shifted))


@dataclass
class Parser:
    """Recursive descent over `alternation > sequence > repetition > atom`."""

    pattern: str
    ignore_case: bool
    position: int = field(default=0, init=False)

    def parse(self) -> z3.ReRef:
        result = self.alternation()
        if self.position != len(self.pattern):
            raise UnsupportedPattern(f"unbalanced parenthesis in {self.pattern!r}")
        return result

    def alternation(self) -> z3.ReRef:
        branches = [self.sequence()]
        while self.peek() == "|":
            self.position += 1
            branches.append(self.sequence())
        return branches[0] if len(branches) == 1 else z3.Union(*branches)

    def sequence(self) -> z3.ReRef:
        pieces = []
        while self.peek() not in {None, "|", ")"}:
            pieces.append(self.repetition())
        if not pieces:
            return z3.Re("")
        return pieces[0] if len(pieces) == 1 else z3.Concat(*pieces)

    def repetition(self) -> z3.ReRef:
        result = self.atom()
        while (mark := self.peek()) in {"*", "+", "?", "{"}:
            self.position += 1
            result = self.repeat(result, mark)
        return result

    def repeat(self, operand: z3.ReRef, mark: str) -> z3.ReRef:
        if mark == "*":
            return z3.Star(operand)
        if mark == "+":
            return z3.Plus(operand)
        if mark == "?":
            return z3.Option(operand)
        return self.interval(operand)

    def interval(self, operand: z3.ReRef) -> z3.ReRef:
        end = self.pattern.find("}", self.position)
        bounds = self.pattern[self.position : end] if end != -1 else ""
        low, comma, high = bounds.partition(",")
        if not low.isdigit() or (comma and high and not high.isdigit()):
            raise UnsupportedPattern(f"invalid interval in {self.pattern!r}")
        self.position = end + 1
        if comma and not high:
            return z3.Concat(z3.Loop(operand, int(low), int(low)), z3.Star(operand))
        return z3.Loop(operand, int(low), int(high or low))

    def atom(self) -> z3.ReRef:
        mark = self.take()
        if mark == "(":
            return self.group()
        if mark == "[":
            return characters(self.bracket())
        if mark == ".":
            return characters(TEXT_CHARACTERS)
        if mark in {"^", "$"}:
            return z3.Re(START if mark == "^" else END)
        if mark == "\\":
            return self.escaped()
        if mark in {"*", "+", "?", "{", ")"}:
            raise UnsupportedPattern(f"nothing to repeat or unbalanced {mark!r} in {self.pattern!r}")
        return self.literal(ord(mark))

    def group(self) -> z3.ReRef:
        if self.peek() == "?":
            raise UnsupportedPattern(f"extension group in {self.pattern!r}")
        result = self.alternation()
        if self.take() != ")":
            raise UnsupportedPattern(f"unbalanced parenthesis in {self.pattern!r}")
        return result

    def escaped(self) -> z3.ReRef:
        mark = self.take()
        if mark.isalnum() or mark in ANCHOR_ESCAPES:
            raise UnsupportedPattern(f"escape \\{mark} in {self.pattern!r}")
        return self.literal(ord(mark))

    def literal(self, code: int) -> z3.ReRef:
        intervals: Intervals = ((code, code),)
        return characters(fold_case(intervals) if self.ignore_case else intervals)

    def bracket(self) -> Intervals:
        negated = self.peek() == "^"
        self.position += negated
        items: list[tuple[int, int]] = []
        first = True
        while (mark := self.take()) != "]" or first:
            items.extend(self.bracket_item(mark))
            first = False
        chosen = normalize(tuple(items))
        chosen = fold_case(chosen) if self.ignore_case else chosen
        return complement_in_text(chosen) if negated else intersect(chosen, TEXT_CHARACTERS)

    def bracket_item(self, mark: str) -> Intervals:
        if mark == "\\":
            raise UnsupportedPattern(
                f"backslash inside a bracket expression in {self.pattern!r}: grep dialects differ"
            )
        if mark == "[" and self.peek() in {"=", "."}:
            raise UnsupportedPattern(f"equivalence or collating element in {self.pattern!r}: locale dependent")
        if mark == "[" and self.peek() == ":":
            return self.posix_class()
        if self.peek() == "-" and self.peek(1) not in {"]", None}:
            self.position += 1
            high = self.take()
            if ord(high) < ord(mark):
                raise UnsupportedPattern(f"reversed range in {self.pattern!r}")
            return ((ord(mark), ord(high)),)
        return ((ord(mark), ord(mark)),)

    def posix_class(self) -> Intervals:
        end = self.pattern.find(":]", self.position)
        name = self.pattern[self.position + 1 : end] if end != -1 else ""
        if name not in POSIX_CLASSES:
            raise UnsupportedPattern(f"character class {name!r} in {self.pattern!r}")
        self.position = end + 2
        return POSIX_CLASSES[name]

    def peek(self, offset: int = 0) -> str | None:
        index = self.position + offset
        return self.pattern[index] if index < len(self.pattern) else None

    def take(self) -> str:
        mark = self.peek()
        if mark is None:
            raise UnsupportedPattern(f"unexpected end of {self.pattern!r}")
        self.position += 1
        return mark
