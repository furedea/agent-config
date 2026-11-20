"""Let a session message only the T3 threads it started.

`t3 thread send` runs outside the sandbox, and its message runs as another agent's turn. A thread
this session started carries a lane's own sandbox and hooks; any other thread may be the user's or
the parent's, so messaging it needs the user's judgment.

The T3 server creates thread ids, so a start records the id only from the launch result that one
plain `t3 thread start --json` call prints: the id is a top-level field, and the agent's reply,
when `--wait` adds one, is a JSON string inside it that cannot forge that field.
"""

import json

import session_store
import shell_syntax
import t3_thread
from session_store import ScopeError, SessionRecord, atomic_json, file_lock, read_json

THREADS_FILE = "t3_threads.json"


def check(record: SessionRecord, command: str) -> None:
    """Refuse a send to any thread this session did not start, wherever the call runs."""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntaxError:
        return
    owned = threads(record)
    for item in commands:
        call = t3_thread.read(item)
        if isinstance(call, t3_thread.Unreadable):
            raise ScopeError(f"T3 thread call may message a thread not started by this session: {call.reason}")
        if call is None or call.action != "send":
            continue
        if call.target not in owned:
            shown = call.target or "chosen at run time"
            raise ScopeError(
                f"T3 thread {shown} was not started by this session; it may be the user's or the parent's"
            )


def confirm(record: SessionRecord, command: str, response: object) -> None:
    """Record the thread that one plain, literal `t3 thread start --json` call launched."""
    try:
        commands = shell_syntax.parse(command)
        simple = len(commands) == 1 and shell_syntax.is_one_simple_command(command)
    except shell_syntax.UnsupportedSyntaxError:
        return
    # Only the t3 found on PATH prints the server's result; a program named by path may be the agent's own script.
    if not simple or commands[0].has_dynamic_words or commands[0].arguments[0] != t3_thread.PROGRAM:
        return
    call = t3_thread.read(commands[0])
    if not isinstance(call, t3_thread.ThreadCall) or call.action != "start" or not call.values("--json"):
        return
    thread = _launched_thread(response)
    if not thread:
        return
    with file_lock(record.directory / ".t3.lock", timeout=session_store.LOCK_WAIT_SECONDS):
        atomic_json(record.directory / THREADS_FILE, {"threads": sorted(threads(record) | {thread})})


def threads(record: SessionRecord) -> set[str]:
    """The ids of the threads this session started, dropping entries that are malformed."""
    path = record.directory / THREADS_FILE
    value = read_json(path).get("threads") if path.exists() else None
    return {item for item in value if isinstance(item, str) and item} if isinstance(value, list) else set()


def _launched_thread(response: object) -> str:
    """The `threadId` of the JSON object a successful call printed; anything failed or malformed gives none."""
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
    thread = result.get("threadId") if isinstance(result, dict) else None
    return thread.strip() if isinstance(thread, str) else ""
