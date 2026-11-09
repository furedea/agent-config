"""Find the lines an allow prefix lets through that a forbidden regex rule would deny (P2 of #73).

An allow prefix covers the lines that are its words, or its words followed by a space and anything
else. A forbidden rule covers the lines its pattern occurs in, less the lines one of its exceptions
occurs in. Where the two meet, the prefix is wider than the rule's carve-out; Z3 names one line in the
overlap so a reader can judge whether the width is intended. Findings are reported, never fixed.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import z3

from tests.ere_to_z3 import (
    END,
    START,
    TEXT_CHARACTERS,
    any_character,
    characters,
    find_line,
    pattern_language,
    search_language,
)


Prefix = tuple[str, ...]


@dataclass(frozen=True)
class Overlap:
    prefix: Prefix
    pattern: str
    witness: str


@dataclass(frozen=True)
class CompiledRule:
    """One forbidden pattern with the exceptions that lift it, compiled once for every prefix."""

    programs: frozenset[str]
    pattern: str
    body: z3.ReRef
    exceptions: tuple[z3.ReRef, ...]

    def governs(self, prefix: Prefix) -> bool:
        return not self.programs or prefix[0] in self.programs

    def denied_from_within(self, span: int) -> z3.ReRef:
        """Lines where the pattern begins within the first `span` characters and no exception applies.

        A pattern that begins only in the free tail after the prefix words holds for every prefix alike,
        so it says nothing about this one.
        """
        anywhere = z3.Star(any_character())
        begins_early = z3.Concat(z3.Loop(any_character(), 0, span), self.body, anywhere)
        if not self.exceptions:
            return begins_early
        return z3.Intersect(begins_early, *(z3.Complement(exception) for exception in self.exceptions))


def find_overlaps(prefixes: Sequence[Prefix], rules: Sequence[dict]) -> tuple[Overlap, ...]:
    compiled = [rule for item in rules for rule in compile_rule(item)]
    found = []
    for prefix in prefixes:
        found.extend(overlaps_of(prefix, compiled))
    return tuple(found)


def compile_rule(rule: dict) -> list[CompiledRule]:
    """A scoped rule reads decoded arguments and ignores case, as the guard does; an unscoped one does neither."""
    ignore_case = "programs" in rule
    exceptions = tuple(search_language(pattern, ignore_case) for pattern in rule.get("exceptions", ()))
    programs = frozenset(rule.get("programs", ()))
    return [
        CompiledRule(programs, pattern, pattern_language(pattern, ignore_case), exceptions)
        for pattern in rule["patterns"]
    ]


def overlaps_of(prefix: Prefix, rules: Sequence[CompiledRule]) -> list[Overlap]:
    covered = z3.Concat(z3.Re(START), prefix_language(prefix), z3.Re(END))
    overlaps = []
    for rule in rules:
        if not rule.governs(prefix):
            continue
        witness = find_line(z3.Intersect(covered, rule.denied_from_within(len(" ".join(prefix)))))
        if witness is not None:
            overlaps.append(Overlap(prefix, rule.pattern, witness))
    return overlaps


def prefix_language(prefix: Prefix) -> z3.ReRef:
    """The words themselves, optionally followed by a space and any text."""
    rest = z3.Concat(z3.Re(" "), z3.Star(characters(TEXT_CHARACTERS)))
    return z3.Concat(z3.Re(" ".join(prefix)), z3.Option(rest))
