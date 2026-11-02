"""Shared fixtures-free helpers for the program_path tests."""

import json
from pathlib import Path

from tests.runtime import REPO_ROOT, load_script_module

guard = load_script_module("agents/hooks/guard_command.py", "guard_command")
policy = load_script_module("agents/hooks/lib/command_policy.py", "command_policy")
GLOBAL_RULES = REPO_ROOT / "agents/hooks/rules/allowed_commands.json"
FORBIDDEN_RULES = REPO_ROOT / "agents/hooks/rules/forbidden_commands.json"
NAME = "[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
PINNED: list[str] = [""]


def pinned_rule(path: str, program: str = "fleetctl") -> dict:
    """An example rule for a program that is not part of the shipped policy."""
    return {
        "programs": [program],
        "program_path": path,
        "patterns": [
            f"^{program} ping$",
            f"^{program} status( --target {NAME})*$",
            f"^{program} run --target {NAME} --note ('[^']*'|[A-Za-z0-9_]+)$",
        ],
        "justification": "Allow the example tool in its documented forms.",
    }


def swe_conform_ledger_rule() -> dict:
    """The rule swe-conform would ship: six subcommands, no hold, pinned to the installed wrapper."""
    name = "[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"
    text = "('[^']*'|\"[^\"$`\\\\!]*\"|[A-Za-z0-9_][A-Za-z0-9._-]*)"
    common = f" --failure {name}| --request-id {name}"
    return {
        "programs": ["ledger"],
        "program_path": "/usr/local/bin/ledger",
        "patterns": [
            "^ledger ping$",
            f"^ledger report({common}| --body {text})*$",
            f"^ledger claim({common})*$",
            f"^ledger status({common})*$",
            f"^ledger release({common}| --generation [0-9]+)*$",
            f"^ledger result({common}| --generation [0-9]+| --result {text})*$",
        ],
        "justification": "Allow the fleet ledger's local spool commands in their documented forms; every other form asks.",
    }


def write_rules(path: Path, rules: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "rules": rules}))
    return path


def verdict(command: str, kind: str = "allowed") -> str:
    return guard.decide(kind, {"tool_input": {"command": command.replace("@fleetctl", PINNED[0])}}).decision
