"""Let a session message, end, or remove only the hc terminals it started.

`hc send`, `hc kill`, and `hc rm` run outside the sandbox: a message runs as another agent's turn
and a kill ends its program. A terminal this session started carries a lane's own sandbox and hooks;
any other may be the user's or the parent's, so driving it needs the user's judgment.

The core assigns addresses such as `t7`, which name one terminal for the core's life, whereas a name
can pass to a later terminal once the first finishes. A start therefore records the address only
from the terminal that one plain `hc run --json` call prints, and targets must use that address.
"""

import json

import hc_terminal
import session_store
import shell_syntax
from session_store import ScopeError, SessionRecord, atomic_json, file_lock, read_json

TERMINALS_FILE = "hc_terminals.json"


def check(record: SessionRecord, command: str) -> None:
    """Refuse a send, kill, or rm to any terminal this session did not start, wherever the call runs."""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntaxError:
        return
    owned = terminals(record)
    for item in commands:
        call = hc_terminal.read(item)
        if isinstance(call, hc_terminal.Unreadable):
            raise ScopeError(f"hc call may drive a terminal not started by this session: {call.reason}")
        if call is None or call.action not in hc_terminal.OWNED_ACTIONS:
            continue
        if call.target not in owned:
            shown = call.target or "chosen at run time"
            raise ScopeError(
                f"hc terminal {shown} was not started by this session; it may be the user's or the parent's"
            )


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
    address = _started_address(response)
    if not address:
        return
    with file_lock(record.directory / ".hc.lock", timeout=session_store.LOCK_WAIT_SECONDS):
        atomic_json(record.directory / TERMINALS_FILE, {"terminals": sorted(terminals(record) | {address})})


def terminals(record: SessionRecord) -> set[str]:
    """The addresses of the terminals this session started, dropping entries that are malformed."""
    path = record.directory / TERMINALS_FILE
    value = read_json(path).get("terminals") if path.exists() else None
    return {item for item in value if isinstance(item, str) and item} if isinstance(value, list) else set()


def _started_address(response: object) -> str:
    """The `address` of the terminal a successful call printed; anything failed or malformed gives none."""
    if isinstance(response, dict):
        if response.get("interrupted") or response.get("is_error") or response.get("isError"):
            return ""
        response = response.get("stdout")
    if not isinstance(response, str):
        return ""
    try:
        result = json.loads(response)
    except ValueError:
        return ""
    address = result.get("address") if isinstance(result, dict) else None
    return address if isinstance(address, str) and "/" not in address else ""
