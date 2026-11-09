"""Find a line that one set of forbidden regex rules denies and another does not (P3 of #73).

A rule denies a line when one of its patterns occurs in it and none of its exceptions does. A rule
scoped to programs applies only to lines that begin with one of them, and reads them without regard
to case, as the guard does. Two rule sets are equal when they deny the same lines.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import z3

from tests.ere_to_z3 import END, START, TEXT_CHARACTERS, characters, find_line, search_language


@dataclass(frozen=True)
class Difference:
    """A line only one side denies: `denied_by` is "source" or "generated"."""

    line: str
    denied_by: str


def find_denial_difference(source: Sequence[dict], generated: Sequence[dict]) -> Difference | None:
    denied = {"source": denial_language(source), "generated": denial_language(generated)}
    for side, other in (("source", "generated"), ("generated", "source")):
        line = find_line(z3.Intersect(denied[side], z3.Complement(denied[other])))
        if line is not None:
            return Difference(line, side)
    return None


def denial_language(rules: Sequence[dict]) -> z3.ReRef:
    """The lines some rule denies, over `START + line + END`."""
    if not rules:
        return z3.Empty(z3.ReSort(z3.StringSort()))
    languages = [rule_language(rule) for rule in rules]
    return languages[0] if len(languages) == 1 else z3.Union(*languages)


def rule_language(rule: dict) -> z3.ReRef:
    ignore_case = "programs" in rule
    patterns = [search_language(pattern, ignore_case) for pattern in rule["patterns"]]
    denied = patterns[0] if len(patterns) == 1 else z3.Union(*patterns)
    clauses = [denied]
    clauses += [z3.Complement(search_language(pattern, ignore_case)) for pattern in rule.get("exceptions", ())]
    if "programs" in rule:
        clauses.append(begins_with_program(rule["programs"]))
    return clauses[0] if len(clauses) == 1 else z3.Intersect(*clauses)


def begins_with_program(programs: Sequence[str]) -> z3.ReRef:
    """Lines whose first word is one of the programs, over `START + line + END`."""
    names = [z3.Re(program) for program in programs]
    program = names[0] if len(names) == 1 else z3.Union(*names)
    rest = z3.Concat(z3.Re(" "), z3.Star(characters(TEXT_CHARACTERS)))
    return z3.Concat(z3.Re(START), program, z3.Option(rest), z3.Re(END))
