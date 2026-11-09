"""Read the command rules each provider is generated with, and compare their decisions with the source (P3 of #73).

Every provider is read as a list of prefix rules and judged with one model: the strictest decision
among the prefixes that begin the command wins, and a command no prefix begins is left undecided.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re


Words = tuple[str, ...]

STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}
CODEX_DECISIONS = {"allow": "allow", "prompt": "ask", "forbidden": "deny"}
UNLISTED_PROGRAM = "zz-unlisted-program"
LONGER_FORM = "zz-longer-form"
CLAUDE_BASH = re.compile(r"Bash\((?P<prefix>.+):\*\)")
DEVIN_EXEC = re.compile(r"Exec\((?P<prefix>[^()]+)\)")
CODEX_RULE = re.compile(r'prefix_rule\(\s*pattern = \[(?P<words>[^\]]*)\],\s*decision = "(?P<decision>\w+)"')
# Claude entries that are not command prefixes and carry no decision of their own to compare.
CLAUDE_NON_PREFIX = frozenset({"Bash(dangerouslyDisableSandbox:true)"})


@dataclass(frozen=True)
class Rule:
    prefix: Words
    decision: str


@dataclass(frozen=True)
class Gap:
    """A command the two rule sets decide differently; None means no rule begins it."""

    words: Words
    source: str | None
    generated: str | None


def policy_rules(rules: Sequence[dict]) -> list[Rule]:
    return [Rule(tuple(rule["prefix"]), rule["decision"]) for rule in rules]


def claude_rules(permissions: Mapping[str, Sequence[str]]) -> list[Rule]:
    """The Bash prefix entries of a Claude permissions object, with every other tool entry left out."""
    return [
        Rule(tuple(match["prefix"].split(" ")), decision)
        for decision in ("allow", "ask", "deny")
        for entry in permissions.get(decision, ())
        if (entry == "Bash" or entry.startswith("Bash(")) and entry not in CLAUDE_NON_PREFIX
        for match in [claude_entry(entry)]
    ]


def claude_entry(entry: str) -> re.Match[str]:
    match = CLAUDE_BASH.fullmatch(entry)
    if match is None:
        raise ValueError(f"unrecognized Claude Bash entry: {entry}")
    return match


def devin_rules(permissions: Mapping[str, Sequence[str]]) -> list[Rule]:
    return [
        Rule(devin_entry(entry), decision)
        for decision in ("allow", "ask", "deny")
        for entry in permissions.get(decision, ())
    ]


def devin_entry(entry: str) -> Words:
    match = DEVIN_EXEC.fullmatch(entry)
    if match is None:
        raise ValueError(f"unrecognized Devin entry: {entry}")
    return tuple(match["prefix"].split(" "))


def codex_rules(text: str) -> list[Rule]:
    """The prefix rules of a Codex rules file; a rule in a layout this does not read is an error, not a skip."""
    matches = list(CODEX_RULE.finditer(text))
    if len(matches) != text.count("prefix_rule("):
        raise ValueError("unrecognized Codex rule: a prefix_rule is not in the pattern, decision layout")
    rules = []
    for match in matches:
        words = tuple(re.findall(r'"((?:[^"\\]|\\.)*)"', match["words"]))
        if match["decision"] not in CODEX_DECISIONS or not words:
            raise ValueError(f"unrecognized Codex rule: {match.group(0)}")
        rules.append(Rule(words, CODEX_DECISIONS[match["decision"]]))
    return rules


def decide(rules: Sequence[Rule], words: Words) -> str | None:
    """The strictest decision among the rules whose prefix begins the command."""
    decisions = [rule.decision for rule in rules if words[: len(rule.prefix)] == rule.prefix]
    return max(decisions, key=STRICTNESS.__getitem__, default=None)


def decision_gaps(source: Sequence[Rule], generated: Sequence[Rule]) -> list[Gap]:
    """Every probe command the two rule sets decide differently.

    A decision depends only on which prefixes begin the command, so the probes are each prefix of
    either set, each shorter form of it, a longer form of it, and a command no prefix begins.
    """
    gaps = []
    for words in probes([*source, *generated]):
        decisions = (decide(source, words), decide(generated, words))
        if decisions[0] != decisions[1]:
            gaps.append(Gap(words, *decisions))
    return gaps


def probes(rules: Sequence[Rule]) -> list[Words]:
    found = {(UNLISTED_PROGRAM,)}
    for rule in rules:
        found.add((*rule.prefix, LONGER_FORM))
        found.update(rule.prefix[:length] for length in range(1, len(rule.prefix) + 1))
    return sorted(found)
