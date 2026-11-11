#!/usr/bin/env -S python3 -IB
"""Evaluate generated prefixes and precise global/project command policy.

Deny prefixes and forbidden patterns stay hard denials. A command that reaches past the sandbox
in a form the precise allowlist does not list, or a command that cannot be inspected statically,
is handed to the user instead of being refused outright.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

import audit_log
import automation_options
import automation_paths
import command_objections
import command_policy
import executing_shell
import foreign_shell_policy
import hook_decision
import hook_input
import literal_words
import shell_syntax
import trusted_owners
from hook_decision import Verdict


@dataclass(frozen=True, slots=True)
class Policy:
    """Generated permission prefixes beside the regex rules of one guard kind.

    `literal_words` is False when the command may not use the rules marked literal_words; those rules
    still count toward the programs the allowed kind governs.
    """

    prefixes: list[dict]
    rules: list[dict]
    literal_words: bool = True
    ignored: trusted_owners.Ignored | None = None

    @property
    def listing_rules(self) -> list[dict]:
        """Rules that may list a command as allowed, excluding the literal_words ones when the command opts out."""
        return self.rules if self.literal_words else command_policy.literal_rules(self.rules, literal=False)


def policies(kind: str, directory: Path) -> Policy:
    """Load required global rules and optional project additions exactly once."""
    permissions = Path(os.environ.get("AGENT_COMMAND_PERMISSIONS", str(directory / "rules/command_permissions.json")))
    name = "allowed_commands.json" if kind == "allowed" else "forbidden_commands.json"
    environment = "AGENT_ALLOWED_COMMAND_RULES" if kind == "allowed" else "AGENT_FORBIDDEN_COMMAND_RULES"
    path = Path(os.environ.get(environment, str(directory / "rules" / name)))
    try:
        prefixes = command_policy.load_rules(permissions, prefixes=True)
    except ValueError as error:
        raise ValueError(f"invalid command permissions: {permissions}") from error
    try:
        rules = command_policy.load_rules(path)
    except ValueError as error:
        if kind == "forbidden":
            raise ValueError(f"forbidden command regex rules were not found or are invalid: {path}") from error
        raise ValueError(f"invalid global {kind} command rules: {path}") from error
    for rule in rules:
        patterns = rule["patterns"]
        rule["patterns"] = patterns + [
            "^" + re.escape(str(Path.home())) + pattern[2:] for pattern in patterns if pattern.startswith("^~/")
        ]
    root = command_policy.project_root()
    if root is None or (project := command_policy.project_file(root, name)) is None:
        return Policy(prefixes, rules)
    try:
        project_rules = command_policy.load_rules(project)
    except ValueError as error:
        raise ValueError(f"invalid project {kind} command rules: {project}") from error
    if kind == "allowed" and (ignored := ignored_project_rules(root, directory)):
        return Policy(prefixes, rules, ignored=ignored)
    taken = command_policy.governed_programs(rules) & set(command_policy.pinned_programs(project_rules))
    if taken:
        raise ValueError(f"project rule pins a program the global rules govern: {', '.join(sorted(taken))}: {project}")
    return Policy(prefixes, rules + project_rules)


def ignored_project_rules(root: Path, directory: Path) -> trusted_owners.Ignored | None:
    """Project allow rules widen what runs unreviewed, so only a trusted owner's repository may add them."""
    path = Path(os.environ.get("AGENT_TRUSTED_OWNERS", str(directory / "rules/trusted_owners.json")))
    return trusted_owners.ignored_rules(root, trusted_owners.load(path))


def decide(kind: str, payload: dict, directory: Path = ROOT) -> Verdict:
    """Decide for an already decoded provider payload, recording every denial and escalation."""
    try:
        policy = policies(kind, directory)
        if not isinstance(payload, dict):
            raise ValueError("failed to parse tool input JSON: expected an object")
        with hook_input.payload_directory(payload):
            verdict = announced(command_verdict(kind, payload, policy), policy)
    except (ValueError, TypeError, AttributeError, OSError) as error:
        prefix = "forbidden command: " if kind == "forbidden" else ""
        verdict = hook_decision.deny(f"BLOCKED: {prefix}{error}\n\n{hook_decision.REVIEW_HINT}")
    _record(verdict, kind, payload)
    return verdict


def announced(verdict: Verdict, policy: Policy) -> Verdict:
    """Tell the user once per project that its allow rules were left out; a denial already explains itself.

    A prompt carries the message in its reason, which survives a provider turning the prompt into a denial.
    """
    if policy.ignored is None or verdict.decision == "deny" or not trusted_owners.announce_once(policy.ignored):
        return verdict
    if verdict.decision == "ask":
        return replace(verdict, reason=f"{verdict.reason}\n\n{policy.ignored.message}")
    return replace(verdict, notice=policy.ignored.message)


def command_verdict(kind: str, payload: dict, policy: Policy) -> Verdict:
    """The first objection any segment raises, then whether the command's settings could redirect a request.

    Rules marked literal_words apply to one plain gh, herdr, curl, or wget call, or a curl call
    piped through known stdin-only filters, with no shell expansions.
    """
    command = payload.get("tool_input", {}).get("command") or ""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntaxError as error:
        preview = shell_syntax.command_preview(command)
        return hook_decision.ask(f"Needs review: {error}.\n\nCommand: {preview}", error.kind)
    if (
        kind == "forbidden"
        and (verdict := command_objections.companion_objection(command, commands)).decision != "allow"
    ):
        return verdict
    if kind == "allowed" and (verdict := command_objections.cleanup_objection(command, commands)).decision != "allow":
        return verdict
    if (
        kind == "allowed"
        and (verdict := command_objections.pinned_program_objection(command, commands, policy)).decision != "allow"
    ):
        return verdict
    if not literal_words.allows_literal_rules(command, commands):
        policy = replace(policy, literal_words=False)
    commands = executing_shell.as_run_by_zsh(payload, commands)
    verdicts = (command_objections.objection(kind, item, policy) for item in commands)
    verdict = next((item for item in verdicts if item.decision != "allow"), hook_decision.ALLOW)
    if verdict.decision == "allow":
        verdict = foreign_shell_policy.objection(commands)
    if kind == "allowed" and verdict.decision == "allow":
        verdict = automation_options.objection(commands)
    if kind == "allowed" and verdict.decision == "allow":
        verdict = automation_paths.objection(payload, commands)
    if kind == "allowed" and verdict.decision == "allow":
        return command_objections.settings_objection(command, commands)
    return verdict


def _record(verdict: Verdict, kind: str, payload: object) -> None:
    if verdict.decision == "allow":
        return
    context = payload if isinstance(payload, dict) else None
    session = payload.get("session_id", "") if isinstance(payload, dict) else ""
    writer = audit_log.blocked if verdict.decision == "deny" else audit_log.escalated
    writer(audit_log.Refusal("Bash", f"guard_{kind}_commands.sh", session, payload=context, detail=verdict.detail))


def check(kind: str, payload: dict, directory: Path = ROOT) -> int:
    """Enforce command policy for an already decoded provider payload."""
    return hook_decision.emit(decide(kind, payload, directory))


def main(arguments: list[str]) -> int:
    """Run the hook for `allowed` or `forbidden` on a JSON payload from stdin and return the exit status.

    Returns 1 on any other arguments and 2, after recording a denial, when stdin is not JSON. Otherwise the status
    is the one `hook_decision.emit` reports for the verdict.
    """
    if len(arguments) != 1 or arguments[0] not in {"allowed", "forbidden"}:
        print("Usage: guard_command.py <allowed|forbidden>", file=sys.stderr)
        return 1
    try:
        payload = json.load(sys.stdin)
    except ValueError, OSError:
        audit_log.blocked(audit_log.Refusal("Bash", f"guard_{arguments[0]}_commands.sh"))
        print("BLOCKED: failed to parse tool input JSON", file=sys.stderr)
        return 2
    return check(arguments[0], payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
