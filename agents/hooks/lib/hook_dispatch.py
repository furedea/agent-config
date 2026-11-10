"""Fan a provider event payload out to the commands declared in a hook manifest."""

import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

DEFAULT_TIMEOUT = 60
DECISION_KEYS = {"decision", "action"}
NOTICE_KEYS = {"systemMessage"}


def run(manifest: Path, event: str, payload: dict) -> int:
    """Run every matching command like the native runtimes do.

    A blocking decision never skips later hooks: audit and guard commands still
    observe the call. The first terminal decision wins on stdout, ahead of any
    systemMessage notice; any exit code 2 makes the dispatch itself a hard block.
    """
    blocked = False
    decision = None
    notice = None
    for hook in _matching_hooks(manifest, event, payload):
        outcome = _run_hook(hook, payload)
        if outcome == 2:
            blocked = True
        elif isinstance(outcome, str) and _is_notice(outcome):
            notice = notice or outcome
        elif isinstance(outcome, str):
            decision = decision or outcome
    if blocked:
        return 2
    if output := decision or notice:
        sys.stdout.write(output + "\n")
    return 0


def _matching_hooks(manifest: Path, event: str, payload: dict) -> Iterator[object]:
    for group in _groups(manifest, event):
        if _matches(group.get("matcher"), payload):
            yield from group.get("hooks") or []


def _groups(manifest: Path, event: str) -> list:
    try:
        data = json.loads(manifest.read_text())
    except OSError, ValueError:
        return []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    groups = hooks.get(event) if isinstance(hooks, dict) else None
    return groups if isinstance(groups, list) else []


def _matches(matcher: object, payload: dict) -> bool:
    if not isinstance(matcher, str) or not matcher:
        return True
    try:
        return re.search(matcher, str(payload.get("tool_name") or "")) is not None
    except re.error:
        return False


def _run_hook(hook: object, payload: dict) -> int | str | None:
    """Return 2 for a hard block, the decision line, or None to keep dispatching."""
    argv = _argv(hook)
    if argv is None:
        return None
    try:
        result = subprocess.run(
            argv,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_timeout(hook),
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode == 2:
        sys.stderr.write(result.stderr)
        return 2
    for line in result.stdout.splitlines():
        if _is_decision(line):
            return line.strip()
    return None


def _argv(hook: object) -> list[str] | None:
    command = hook.get("command") if isinstance(hook, dict) else None
    if not isinstance(command, str) or not command.strip():
        return None
    try:
        return shlex.split(os.path.expandvars(command))
    except ValueError:
        return None


def _timeout(hook: object) -> float:
    value = hook.get("timeout") if isinstance(hook, dict) else None
    if not isinstance(value, int | float | str):
        return float(DEFAULT_TIMEOUT)
    try:
        return float(value)
    except TypeError, ValueError:
        return float(DEFAULT_TIMEOUT)


def _is_decision(line: str) -> bool:
    return bool(_keys(line) & (DECISION_KEYS | NOTICE_KEYS))


def _is_notice(line: str) -> bool:
    """A notice informs the provider without deciding, so any decision outranks it."""
    keys = _keys(line)
    return bool(keys & NOTICE_KEYS) and not keys & DECISION_KEYS


def _keys(line: str) -> set[str]:
    line = line.strip()
    if not line.startswith("{"):
        return set()
    try:
        data = json.loads(line)
    except ValueError:
        return set()
    return set(data) if isinstance(data, dict) else set()
