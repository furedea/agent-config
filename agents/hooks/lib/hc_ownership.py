"""Let a session start lanes only in its own checkouts, and drive only the hc terminals it started.

`hc run`, `hc send`, `hc kill`, and `hc rm` run outside the sandbox. A lane's sandbox is rooted in the
directory it starts in, so `--cwd` must stay inside this session's checkout or a lane worktree this
session created. A message runs as another agent's turn and a kill ends its program; a terminal this
session started carries a lane's own sandbox and hooks, whereas any other may be the user's or the
parent's, so driving it needs the user's judgment.

A name can pass to a later terminal once the first finishes, and an address such as `t7` is unique
only within one core, so a start records the address together with the creation time that one plain
`hc run --json` call prints, and each target must still be that terminal when the core is asked.
"""

import json
import subprocess
from pathlib import Path

import hc_terminal
import herdr_ownership
import session_store
import shell_syntax
from session_store import ScopeError, SessionRecord, atomic_json, file_lock, read_json

TERMINALS_FILE = "hc_terminals.json"
LIVE_TIMEOUT_SECONDS = 5


def check(record: SessionRecord, command: str) -> None:
    """Refuse a lane rooted outside this session's checkouts and a drive of a terminal it did not start."""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntaxError:
        return
    for item in commands:
        call = hc_terminal.read(item)
        if isinstance(call, hc_terminal.Unreadable):
            raise ScopeError(f"hc call may drive a terminal not started by this session: {call.reason}")
        if call is None:
            continue
        if call.action == "run":
            _require_lane_directory(record, call.values("--cwd"))
        elif call.action in hc_terminal.OWNED_ACTIONS:
            _require_started(record, call.target)


def confirm(record: SessionRecord, command: str, response: object) -> None:
    """Record the terminal that one plain, literal `hc run --json` call started."""
    try:
        commands = shell_syntax.parse(command)
        simple = len(commands) == 1 and shell_syntax.is_one_simple_command(command)
    except shell_syntax.UnsupportedSyntaxError:
        return
    # Only the hc found on PATH prints the core's result; a program named by path may be the agent's own script.
    if not simple or commands[0].has_dynamic_words or commands[0].arguments[0] != hc_terminal.PROGRAM:
        return
    if commands[0].assignments or commands[0].wrapper_depth:
        return
    call = hc_terminal.read(commands[0])
    if not isinstance(call, hc_terminal.TerminalCall) or call.action != "run" or not call.values("--json"):
        return
    started = _started_terminal(response)
    if started is None:
        return
    with file_lock(record.directory / ".hc.lock", timeout=session_store.LOCK_WAIT_SECONDS):
        atomic_json(record.directory / TERMINALS_FILE, {"terminals": terminals(record) | dict([started])})


def terminals(record: SessionRecord) -> dict[str, int]:
    """The creation time of each terminal this session started, by address, dropping malformed entries."""
    path = record.directory / TERMINALS_FILE
    value = read_json(path).get("terminals") if path.exists() else None
    if not isinstance(value, dict):
        return {}
    return {address: created for address, created in value.items() if _is_address(address) and _is_time(created)}


def _require_lane_directory(record: SessionRecord, directories: list[str]) -> None:
    for directory in directories:
        roots = [
            record.root,
            *(Path(path) for path in herdr_ownership.created_worktrees(record)),
        ]
        path = Path(directory)
        if not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in roots):
            raise ScopeError(
                f"hc run --cwd {directory} is outside this session's checkout and the lane worktrees it created"
            )


def _require_started(record: SessionRecord, target: str | None) -> None:
    created = terminals(record).get(target or "")
    if created is None:
        shown = target or "chosen at run time"
        raise ScopeError(f"hc terminal {shown} was not started by this session; it may be the user's or the parent's")
    if _live_creation_time(target or "") != created:
        raise ScopeError(f"hc terminal {target} now names another terminal than the one this session started")


def _live_creation_time(address: str) -> int | None:
    """When the terminal the core now holds at the address was created; an unreachable core cannot vouch."""
    try:
        result = subprocess.run(
            ["hc", "get", address, "--json"], capture_output=True, text=True, check=True, timeout=LIVE_TIMEOUT_SECONDS
        )
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise ScopeError(f"hc get {address} failed, so ownership cannot be checked") from error
    created = value.get("created_ms") if isinstance(value, dict) else None
    return created if _is_time(created) else None


def _started_terminal(response: object) -> tuple[str, int] | None:
    """The address and creation time a successful call printed; anything failed or malformed gives none."""
    if isinstance(response, dict):
        if response.get("interrupted") or response.get("is_error") or response.get("isError"):
            return None
        response = response.get("stdout")
    if not isinstance(response, str):
        return None
    try:
        result = json.loads(response)
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    address, created = result.get("address"), result.get("created_ms")
    return (address, created) if _is_address(address) and _is_time(created) else None


def _is_address(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "/" not in value


def _is_time(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
