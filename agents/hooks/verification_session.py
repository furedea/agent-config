#!/usr/bin/env -S python3 -IB
"""Mechanical lifecycle entry points for registered verification sessions."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "lib"))

import herdr_ownership
import hook_input
import patch_input
import session_gate
from session_snapshot import repository_root
from session_store import (
    LockTimeoutError,
    ScopeError,
    SessionKey,
    SessionRecord,
    StateError,
    file_lock,
    load,
    prune,
    register,
    resume,
    session_directory,
)

EVENTS = ("session-start", "pre-tool-use", "post-tool-use", "stop", "session-end")


def main() -> int:
    """Run one hook event or explicit command, print its JSON result, and return the process exit status.

    Native events (`codex|claude <event>`) read the provider payload from stdin and always exit 0 so a failure becomes
    a hook decision instead of a crashed hook. Explicit `verify` and `status` commands exit 1 on an unresolved
    verification or an error, and a malformed command line prints the usage to stderr and exits 1 (0 for help).
    """
    arguments = sys.argv[1:]
    query = len(arguments) == 2 and arguments[0] == "status"
    explicit = query or (
        2 <= len(arguments) <= 3 and arguments[0] == "verify" and arguments[1:-1] in ([], ["--force"])
    )
    native = len(arguments) == 2 and arguments[0] in {"codex", "claude"} and arguments[1] in EVENTS
    if not (explicit or native):
        print(
            "Usage: verification_session.py codex|claude session-start|pre-tool-use|post-tool-use|stop|session-end\n"
            "       verification_session.py verify [--force] /path/to/session-record\n"
            "       verification_session.py status /path/to/session-record\n"
            "Native events read the provider hook input from stdin.",
            file=sys.stderr,
        )
        return 0 if arguments in (["-h"], ["--help"]) else 1
    event = arguments[0] if explicit else arguments[1]
    status = 0
    payload: dict = {}
    try:
        if explicit:
            result, status = _explicit_result(arguments)
        else:
            payload = _hook_payload()
            result = dispatch(arguments[0], event, payload)
    except (OSError, ValueError, TypeError, KeyError) as error:
        result = failure(event, payload, error)
        status = int(explicit)
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return status


def dispatch(provider: str, event: str, payload: dict) -> dict[str, object]:
    """Route a native hook event to its lifecycle action and return the provider's JSON answer."""
    record = _registered_record(provider, payload, starting=event == "session-start")
    if event == "pre-tool-use":
        _check_scope(record, payload)
    elif event == "post-tool-use":
        _confirm_tool(record, payload)
    elif event == "stop":
        return {**session_gate.stop(record, stop_hook_active=bool(payload.get("stop_hook_active")))}
    elif event == "session-end":
        _end_session(record)
        prune()
    elif event == "session-start":
        prune()
        return {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"Verification record: {record.directory}",
            }
        }
    return {}


def _registered_record(provider: str, payload: dict, *, starting: bool = False) -> SessionRecord:
    """Find the record registered for the payload's session, or create it when the session is starting."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise StateError("Missing absolute session working directory")
    root = repository_root(Path(cwd))
    session = payload.get("session_id")
    if not isinstance(session, str):
        raise StateError("Missing provider session ID")
    directory = session_directory(SessionKey(root.resolve(), provider, session))
    if starting:
        # New IDs after clear/fork have no reliable predecessor in native hook input.
        start = register if payload.get("source") == "startup" else resume
        return start(root, provider, session)
    if not directory.exists():
        raise StateError("Missing verification registration; restart or resume to run SessionStart in this worktree")
    record = load(directory)
    if record.results().get("session_id") != session or record.provider != provider:
        raise StateError("Provider session differs from the registered session")
    record.touch()
    return record


def _check_scope(record: SessionRecord, payload: dict) -> None:
    """Check the paths a tool names; the sandbox, not this check, confines what a shell command writes."""
    value = payload.get("tool_input", {})
    if not isinstance(value, dict):
        raise StateError("Invalid tool input")
    cwd = Path(payload["cwd"])
    for key in ("cwd", "workdir"):
        if directory := value.get(key):
            _require_inside(record, cwd / directory)
    command = value.get("command", value.get("cmd", ""))
    if isinstance(command, str):
        herdr_ownership.check(record, command)
    try:
        patch = hook_input.patch_body(value, payload.get("tool_name"))
    except ValueError as error:
        raise StateError(str(error)) from error
    for filename in patch_input.paths(patch):
        _require_inside(record, cwd / filename)
    if payload.get("tool_name") in {"Write", "Edit", "MultiEdit", "apply_patch"}:
        if filename := value.get("file_path"):
            _require_inside(record, cwd / filename)


def _require_inside(record: SessionRecord, path: Path) -> None:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(record.root) or any(
        resolved.is_relative_to(root) for root in hook_input.temporary_roots()
    ):
        return
    raise ScopeError(f"Tool target {resolved} is outside the registered worktree {record.root}")


def _confirm_tool(record: SessionRecord, payload: dict) -> None:
    value = payload.get("tool_input", {})
    command = value.get("command", value.get("cmd", "")) if isinstance(value, dict) else ""
    if isinstance(command, str):
        herdr_ownership.confirm(record, command, payload.get("tool_response"))


def _end_session(record: SessionRecord) -> None:
    """Mark an idle session ended, leaving busy verification to mtime-based GC."""
    try:
        # Codex gives SessionEnd only 3 seconds; a running Stop keeps the session alive.
        with file_lock(record.directory / ".lock", timeout=2):
            record.end()
    except LockTimeoutError:
        pass


def failure(event: str, payload: dict, error: Exception) -> dict[str, object]:
    """Turn an unresolved hook error into the event's decision: ask on scope escapes, otherwise deny or block."""
    message = f"Verification unresolved · {error}"
    if event == "pre-tool-use":
        escalated = isinstance(error, ScopeError)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask" if escalated else "deny",
                "permissionDecisionReason": f"Needs review · {error}" if escalated else message,
            }
        }
    if event in {"stop", "verify"} and not payload.get("stop_hook_active"):
        return {"decision": "block", "reason": message}
    return {"systemMessage": message}


def _explicit_result(arguments: list[str]) -> tuple[dict, int]:
    """Answer a status query or verify a session record, with the exit status the command reports."""
    record = load(Path(arguments[-1]))
    if arguments[0] == "status":
        return session_gate.status(record), 0
    result = session_gate.gate(record, force="--force" in arguments)
    return result, int(result.get("decision") == "block" or session_gate.unresolved(record))


def _hook_payload() -> dict:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise StateError("Hook input must be an object")
    return payload


if __name__ == "__main__":
    sys.exit(main())
