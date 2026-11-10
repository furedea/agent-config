"""Find the lines an allow prefix lets through that a forbidden regex rule would deny (P2 of #73).

An allow prefix covers the lines that are its words, or its words followed by a space and anything
else. A forbidden rule covers the lines its pattern occurs in, less the lines one of its exceptions
occurs in. Where the two meet, the prefix is wider than the rule's carve-out; Z3 names one line in the
overlap so a reader can judge whether the width is intended. Findings are reported, never fixed.
"""

from collections.abc import Collection, Sequence
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
# Mirrors shell_wrappers.COMMAND_LOOKUP; test_forbidden_overlap pins the two together.
COMMAND_LOOKUP = frozenset({"-v", "-V"})


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
        return self.without_exceptions(z3.Loop(any_character(), 0, span))

    def denied_command(self) -> z3.ReRef:
        """Commands the pattern occurs in, wherever it begins, once no exception applies.

        The program must also be one the rule governs.
        """
        denied = self.without_exceptions(z3.Star(any_character()))
        if not self.programs:
            return denied
        return z3.Intersect(denied, self.run_by_program())

    def without_exceptions(self, lead: z3.ReRef) -> z3.ReRef:
        begins = z3.Concat(lead, self.body, z3.Star(any_character()))
        if not self.exceptions:
            return begins
        return z3.Intersect(begins, *(z3.Complement(exception) for exception in self.exceptions))

    def run_by_program(self) -> z3.ReRef:
        """Commands whose first word is one of the programs the rule governs."""
        names = z3.Union(*(z3.Re(program) for program in sorted(self.programs)))
        rest = z3.Concat(z3.Re(" "), z3.Star(any_character()))
        return z3.Concat(z3.Re(START), names, z3.Union(z3.Re(END), rest))


def find_overlaps(
    prefixes: Sequence[Prefix], rules: Sequence[dict], wrappers: Collection[str] = ()
) -> tuple[Overlap, ...]:
    """Overlaps of each prefix with the rules.

    A prefix that starts with a name in `wrappers` runs the text after its words as a command, so that
    command is compared with the rules from its own start; the wrapper's options are left in that text.
    """
    for prefix in prefixes:
        require_single_words(prefix)
    compiled = [rule for item in rules for rule in compile_rule(item)]
    found = []
    for prefix in prefixes:
        if is_command_lookup(prefix):
            continue
        found.extend(wrapped_overlaps_of(prefix, compiled) if prefix[0] in wrappers else overlaps_of(prefix, compiled))
    return tuple(found)


def is_command_lookup(prefix: Prefix) -> bool:
    """`command -v` only looks a name up, so nothing the rules forbid runs through it."""
    return prefix[0] == "command" and len(prefix) > 1 and prefix[1] in COMMAND_LOOKUP


def wrapped_overlaps_of(prefix: Prefix, rules: Sequence[CompiledRule]) -> list[Overlap]:
    overlaps = []
    for rule in rules:
        inner = find_line(rule.denied_command())
        if inner is not None:
            overlaps.append(Overlap(prefix, rule.pattern, f"{' '.join(prefix)} {inner}"))
    return overlaps


def require_single_words(prefix: Prefix) -> None:
    """Joining the words with spaces would merge arguments the provider keeps apart, so such a prefix is refused."""
    for word in prefix:
        if not word or any(character.isspace() for character in word):
            raise ValueError(f"prefix word must be one non-empty word without whitespace: {prefix!r}")


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
