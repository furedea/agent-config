"""A malformed gh policy table blocks every gh decision instead of widening what runs unprompted."""

from pathlib import Path

import pytest
from tests.runtime import load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
pytestmark = pytest.mark.usefixtures("isolated_project")


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"version": 2, "grants": [], "commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [{"target": "any", "effects": ["read"], "decision": "allow"}], '
        '"commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [{"target": "anyone", "effects": ["read"], "decision": "allow", '
        '"justification": "x"}], "commands": {}, "rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [], "commands": {"pr view": {"operation": "pr.view", "effect": "maybe"}}, '
        '"rest": [], "graphql_mutations": {}}',
        '{"version": 1, "grants": [], "commands": {}, "rest": [{"method": "POST", "path": "repos/*", '
        '"operation": "x.y", "effect": "reversible"}], "graphql_mutations": {}}',
    ],
    ids=["not JSON", "a newer version", "no justification", "an unknown target", "an unknown effect", "a bad path"],
)
def test_a_malformed_policy_table_blocks_instead_of_widening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    path = tmp_path / "gh_policy.json"
    path.write_text(content)
    monkeypatch.setenv("AGENT_GH_POLICY", str(path))
    verdict = guard.decide("allowed", {"tool_input": {"command": "gh pr list"}})
    assert verdict.decision == "deny"
    assert "invalid gh policy" in verdict.reason
