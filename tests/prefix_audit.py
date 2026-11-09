"""Audit shared command prefixes for conflicts, ineffective entries, and redundancy (P1 of #73).

Both providers resolve overlapping prefixes to the strictest decision, so an entry is judged against
the entries whose prefix it extends. The audit only reports; it never rewrites a rule.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations

Prefix = tuple[str, ...]

STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}


@dataclass(frozen=True)
class Finding:
    """An entry and the other entry that overlaps it."""

    prefix: Prefix
    decision: str
    covered_by: Prefix
    covering_decision: str


@dataclass(frozen=True)
class PrefixAudit:
    conflicts: tuple[Finding, ...]
    ineffective: tuple[Finding, ...]
    redundant: tuple[Finding, ...]


@dataclass(frozen=True)
class Entry:
    prefix: Prefix
    decision: str

    def extends(self, other: Entry) -> bool:
        return self.prefix[: len(other.prefix)] == other.prefix

    def findings_against(self, other: Entry) -> Finding:
        return Finding(self.prefix, self.decision, other.prefix, other.decision)


def audit_prefixes(rules: Sequence[dict]) -> PrefixAudit:
    entries = [Entry(tuple(rule["prefix"]), rule["decision"]) for rule in rules]
    pairs = [(first, second) for first, second in combinations(entries, 2)]
    return PrefixAudit(
        conflicts=tuple(later.findings_against(earlier) for earlier, later in pairs if is_conflict(earlier, later)),
        ineffective=tuple(extra for extra in ordered_findings(pairs) if is_ineffective(extra)),
        redundant=tuple(extra for extra in ordered_findings(pairs) if is_redundant(extra)),
    )


def is_conflict(earlier: Entry, later: Entry) -> bool:
    return earlier.prefix == later.prefix and earlier.decision != later.decision


def ordered_findings(pairs: list[tuple[Entry, Entry]]) -> list[Finding]:
    """Each pair read with the longer prefix as the covered entry; equal prefixes are covered by the earlier one."""
    findings = []
    for first, second in pairs:
        if second.extends(first):
            findings.append(second.findings_against(first))
        elif first.extends(second):
            findings.append(first.findings_against(second))
    return findings


def is_ineffective(finding: Finding) -> bool:
    if finding.prefix == finding.covered_by:
        return False
    return STRICTNESS[finding.covering_decision] > STRICTNESS[finding.decision]


def is_redundant(finding: Finding) -> bool:
    return finding.decision == finding.covering_decision
