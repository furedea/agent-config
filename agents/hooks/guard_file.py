#!/usr/bin/env -S python3 -IB
"""Enforce file-boundary policies and scan content without logging secret bodies."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib"))

import audit_log
from command_policy import regex_matches
import git_safety
import hook_input
import shell_syntax


UNKNOWN_REPOSITORY = (
    "cannot tell which repository this commit uses, because a shell expansion or a directory stack picks it.\n\n"
    "Run git commit from the repository, or name it with a literal cd or git -C path."
)


def policy_path(environment: str, name: str, directory: Path) -> Path:
    return Path(os.environ.get(environment, str(directory / "rules" / name)))


def load_policy(path: Path, field: str) -> list:
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("unsupported policy version")
        values = data.get(field)
        if not isinstance(values, list) or not values:
            raise ValueError("empty policy")
        return values
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid policy: {path}") from error


def protected_reason(value: str, path: Path) -> str:
    try:
        paths = load_policy(path, "paths")
        if not all(isinstance(item, str) and item for item in paths):
            raise ValueError("invalid path")
    except ValueError as error:
        raise ValueError(f"invalid protected path policy: {path}") from error
    if os.path.expanduser(value) not in {os.path.expanduser(item) for item in paths}:
        return ""
    return (
        f"{value} is part of the agent harness boundary.\n\n"
        "Change the source under agents/ in the agent-config repository, then regenerate the installed files. "
        "The provider permissions and sandbox remain the hard boundary."
    )


def commit_filename_rules(path: Path) -> list[dict]:
    try:
        rules = load_policy(path, "rules")
        for rule in rules:
            validate_filename_rule(rule)
        return rules
    except ValueError as error:
        raise ValueError(f"invalid secret commit policy: {path}") from error


def validate_filename_rule(rule: object) -> None:
    if not isinstance(rule, dict) or not all(
        isinstance(rule.get(key), str) and rule[key] for key in ("pattern", "reason")
    ):
        raise ValueError("invalid secret filename rule")
    regex_matches(rule["pattern"], "")


def staged_filename_matches(rules: list[dict], location: tuple[str, ...]) -> list[tuple[str, str]]:
    """Return rejected filenames and policy reasons, never staged file contents."""
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *location, "diff", "--cached", "--name-only", "-z"],
        capture_output=True,
        check=True,
    )
    matches = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        name = os.fsdecode(raw)
        reason = next((rule["reason"] for rule in rules if regex_matches(rule["pattern"], name, insensitive=True)), "")
        if reason:
            matches.append((name, reason))
    return matches


def commit_reason(command: str, directory: Path) -> str:
    locations = commit_locations(command)
    if not locations:
        return ""
    path = policy_path("AGENT_SECRET_COMMIT_POLICY", "secret_commit_policy.json", directory)
    rules = commit_filename_rules(path)
    matches = [match for location in locations for match in staged_filename_matches(rules, location)]
    if not matches:
        return ""
    files = "\n".join(f"  - {name} ({reason})" for name, reason in matches)
    return (
        "Commit rejected — staged files may contain secrets.\n\n"
        f"The following files match sensitive filename patterns and must not be committed:\n{files}\n\n"
        "Unstage these files and exclude secrets from version control. Ask the user if unsure."
    )


def commit_locations(command: str) -> list[tuple[str, ...]]:
    """The Git options that select the repository of each commit, following any cd before it.

    Only path options are kept: a -c from the command would let it run configured programs here.
    """
    directory: Path | None = Path.cwd()
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntax:
        return [("-C", str(directory))] if re.match(r"^\s*git\s+commit", command) else []
    locations = []
    for item in commands:
        if Path(item.arguments[0]).name in {"cd", "pushd", "popd"}:
            directory = changed_directory(directory, item)
        elif (options := commit_path_options(item)) is None:
            continue
        elif directory is None:
            raise ValueError(UNKNOWN_REPOSITORY)
        else:
            locations.append(("-C", str(directory), *options))
    return list(dict.fromkeys(locations))


def changed_directory(directory: Path | None, item: shell_syntax.Command) -> Path | None:
    """Follow a cd or pushd to a literal directory; any other change leaves the directory unknown."""
    name, arguments = Path(item.arguments[0]).name, item.arguments
    operands = [index for index, argument in enumerate(arguments[1:], 1) if not argument.startswith("-")]
    if directory is None or name == "popd" or "-" in arguments or (name == "pushd" and not operands):
        return None
    if not operands:
        return Path.home()
    index = operands[0]
    return None if item.dynamic[index] else directory / arguments[index]


def commit_path_options(item: shell_syntax.Command) -> tuple[str, ...] | None:
    """The global path options of a git commit, or None for any other command."""
    if Path(item.arguments[0]).name != "git":
        return None
    try:
        globals_, command = git_safety.git_arguments(item.arguments)
    except ValueError:
        return None
    if command[:1] != ("commit",):
        return None
    if any(item.dynamic[1 : 1 + len(globals_)]):
        raise ValueError(UNKNOWN_REPOSITORY)
    options: list[str] = []
    index = 0
    while index < len(globals_):
        option = globals_[index]
        if option in {"-C", "--git-dir", "--work-tree"}:
            options += globals_[index : index + 2]
        elif option.startswith(("--git-dir=", "--work-tree=")):
            options.append(option)
        index += 2 if option in {"-C", "-c", "--git-dir", "--work-tree"} else 1
    return tuple(options)


def content_text(mode: str, payload: dict) -> str:
    values = payload.get("tool_input") or {}
    if mode == "prompt":
        return payload.get("prompt") or ""
    if mode == "write":
        return "".join(values.get(key) or "" for key in ("content", "new_string", "new_source"))
    # Grep may name a directory; only a single file target can be scanned before the tool runs.
    path = hook_input.file_path(values)
    if not path or not Path(path).is_file():
        return ""
    with Path(path).open("rb") as stream:
        return stream.read(100000).decode(errors="replace")


def content_match(text: str, path: Path) -> tuple[str, str] | None:
    # Preserve the existing optional scanner contract; path guards are separate.
    if not text or not path.is_file():
        return None
    rules = json.loads(path.read_text())
    for name in sorted(rules):
        rule = rules[name]
        if not rule.get("pattern"):
            continue
        result = subprocess.run(
            ["rg", "--pcre2", "-q", "-e", rule["pattern"], "-"],
            input=text + "\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode > 1:
            raise ValueError(f"invalid sensitive content rule: {name}")
        if result.returncode == 0:
            return name, rule.get("message", "Sensitive information detected")
    return None


def scan_content(mode: str, payload: dict, directory: Path) -> None:
    match = content_match(
        content_text(mode, payload),
        policy_path("AGENT_SECRET_CONTENT_PATTERNS", "secret_content_patterns.json", directory),
    )
    if match is None:
        return
    name, message = match
    reason = f"{message} ({name})"
    values = payload.get("tool_input") or {}
    tool = (
        "UserPromptSubmit" if mode == "prompt" else "Read" if mode == "read" else payload.get("tool_name") or "Write"
    )
    summary = "<prompt body elided>" if mode == "prompt" else hook_input.file_path(values)
    audit_log.blocked(
        audit_log.Refusal(
            tool,
            "guard_secret_content.sh",
            payload.get("session_id") or "",
            payload=payload,
            targets=() if mode == "prompt" else ((summary,) if summary else ()),
        )
    )
    if mode == "prompt":
        decision = {"decision": "block", "reason": f"BLOCKED: {reason}. Prompt contains sensitive information."}
    elif payload.get("provider") in {"devin", "hermes", "pi"}:
        decision = {"decision": "block", "reason": f"BLOCKED: {reason}"}
    else:
        decision = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"BLOCKED: {reason}",
            }
        }
    print(json.dumps(decision))


def check(mode: str, payload: dict, directory: Path = ROOT) -> int:
    """Enforce file policy without spawning another hook process."""
    value = ""
    tool = "Bash" if mode == "commit" else "Edit"
    hook = "guard_secret_commit.sh" if mode == "commit" else "guard_harness_files.sh"
    try:
        if mode in {"prompt", "read", "write"}:
            scan_content(mode, payload, directory)
            return 0
        values = payload.get("tool_input") or {}
        tool = payload.get("tool_name") or tool
        value = values.get("command") or "" if mode == "commit" else hook_input.file_path(values)
        if not value:
            return 0
        reason = (
            commit_reason(value, directory)
            if mode == "commit"
            else protected_reason(value, policy_path("AGENT_PROTECTED_PATH_POLICY", "protected_paths.json", directory))
        )
        if not reason:
            return 0
    except (OSError, ValueError, TypeError, AttributeError, subprocess.CalledProcessError) as error:
        reason = str(error)
    audit_log.blocked(
        audit_log.Refusal(
            tool,
            hook,
            payload.get("session_id", "") if isinstance(payload, dict) else "",
            payload=payload if isinstance(payload, dict) else None,
            targets=() if mode == "commit" else ((value,) if value else ()),
        )
    )
    print(f"BLOCKED: {reason}", file=sys.stderr)
    return 2


def main(arguments: list[str]) -> int:
    if len(arguments) != 1 or arguments[0] not in {"harness", "commit", "prompt", "read", "write"}:
        print("Usage: guard_file.py <harness|commit|prompt|read|write>", file=sys.stderr)
        return 1
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError) as error:
        tool = "Bash" if arguments[0] == "commit" else "Edit"
        hook = "guard_secret_commit.sh" if arguments[0] == "commit" else "guard_harness_files.sh"
        audit_log.blocked(audit_log.Refusal(tool, hook))
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return check(arguments[0], payload)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
