"""P1: the shared command prefixes hold no conflicting, ineffective, or newly redundant entry.

Both providers resolve overlapping prefixes to the strictest decision (Claude reads deny, ask, then allow;
Codex lets the most restrictive win), so one ancestor-based model covers them.
"""

import json

from tests.prefix_audit import Finding, audit_prefixes
from tests.runtime import REPO_ROOT


RULES = json.loads((REPO_ROOT / "agents/command_permissions.json").read_text())["rules"]

# Reported by the first P1 run (#73). Remove an entry in the change that merges it into its ancestor.
KNOWN_REDUNDANT = {
    (("cargo", "fmt", "--check"), ("cargo", "fmt")),
    (("nixfmt", "--check"), ("nixfmt",)),
    (("node", "--test"), ("node",)),
    (("oxfmt", "--check"), ("oxfmt",)),
    (("pnpm", "exec", "oxfmt", "--check"), ("pnpm", "exec", "oxfmt")),
    (("stylua", "--check"), ("stylua",)),
    (("tex-fmt", "--check"), ("tex-fmt",)),
}


def describe(findings: tuple[Finding, ...]) -> list[str]:
    return [
        f"{' '.join(item.prefix)} ({item.decision}) vs {' '.join(item.covered_by)} ({item.covering_decision})"
        for item in findings
    ]


def test_no_prefix_has_two_decisions() -> None:
    assert describe(audit_prefixes(RULES).conflicts) == []


def test_every_prefix_takes_effect() -> None:
    assert describe(audit_prefixes(RULES).ineffective) == []


def test_redundant_prefixes_are_only_the_known_ones() -> None:
    found = {(item.prefix, item.covered_by) for item in audit_prefixes(RULES).redundant}
    assert found == KNOWN_REDUNDANT
