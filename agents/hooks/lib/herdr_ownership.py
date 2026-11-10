"""Let a session prompt only the Herdr agents it started.

Herdr runs outside the sandbox, so text sent to a pane runs there too. An agent this session
started carries the same sandbox and hooks, so prompting it is safe; any other target may be the
user's own shell or session, and prompting it needs the user's judgment.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import TypeGuard

import session_store
import shell_syntax
from herdr_grammar import has_global_option
from session_store import ScopeError, SessionRecord, atomic_json, file_lock, read_json

AGENTS_FILE = "herdr_agents.json"
LIST_TIMEOUT_SECONDS = 5


def check(record: SessionRecord, command: str) -> None:
    """Refuse ownership actions that cannot be tied to this session's terminals."""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntax:
        return
    for parsed in commands:
        action = parsed.arguments[1:3]
        if (
            parsed.program_is_dynamic
            or Path(parsed.arguments[0]).name != "herdr"
            or (
                not has_global_option(parsed.arguments)
                and action
                not in {
                    ("agent", "start"),
                    ("agent", "prompt"),
                    ("workspace", "close"),
                    ("worktree", "remove"),
                    ("agent", "rename"),
                }
            )
        ):
            continue
        simple = _is_single_call(command, commands)
        if not simple or "--group" in parsed.arguments:
            raise ScopeError("Herdr ownership actions need one simple direct Herdr call")
        if action == ("agent", "start"):
            _claim(_target(parsed))
        elif action == ("agent", "prompt"):
            _require_owned(record, _target(parsed))
        elif action == ("workspace", "close"):
            _require_closable(record, parsed)
        elif action == ("worktree", "remove"):
            _require_removable(record, parsed)
        else:
            raise ScopeError("Renaming a Herdr agent could hand one of this session's names to another pane")


def confirm(record: SessionRecord, command: str, response: object) -> None:
    """Update ownership only for matching successful results of one simple direct call."""
    try:
        commands = shell_syntax.parse(command)
    except shell_syntax.UnsupportedSyntax:
        return
    if not _is_single_call(command, commands):
        return
    parsed = commands[0]
    if any(parsed.dynamic):
        return
    result = created_result(response)
    action = parsed.arguments[1:3]
    expected = {
        ("workspace", "create"): "workspace_created",
        ("worktree", "create"): "worktree_created",
        ("agent", "start"): "agent_started",
        ("workspace", "close"): "ok",
        ("worktree", "remove"): "worktree_removed",
    }.get(action)
    if expected is None or result.get("type") != expected:
        return
    with file_lock(record.directory / ".herdr.lock", timeout=session_store.LOCK_WAIT_SECONDS):
        _record_result(record, parsed, result)


def _record_result(record: SessionRecord, parsed: shell_syntax.Command, result: dict) -> None:
    action = parsed.arguments[1:3]
    if action in {("workspace", "create"), ("worktree", "create")}:
        _record_workspace(record, parsed, result)
    elif action in {("workspace", "close"), ("worktree", "remove")}:
        workspace = _target(parsed) if action[0] == "workspace" else result.get("workspace_id", "")
        _expire_workspace(record, workspace)
    elif action == ("agent", "start"):
        agent = result.get("agent")
        if (
            _valid_entry(agent, ("name", "terminal_id", "pane_id", "workspace_id"))
            and _agent_session(agent)
            and agent["name"] == _target(parsed)
        ):
            _save(record, agents={**entries(record, "agents"), agent["name"]: agent})


def _is_single_call(command: str, commands: tuple[shell_syntax.Command, ...]) -> bool:
    try:
        return (
            len(commands) == 1
            and commands[0].arguments[0] == "herdr"
            and not has_global_option(commands[0].arguments)
            and shell_syntax.is_one_simple_command(command)
        )
    except shell_syntax.UnsupportedSyntax:
        return False


def _target(parsed: shell_syntax.Command) -> str:
    if len(parsed.arguments) < 4 or parsed.dynamic[3]:
        return ""
    return parsed.arguments[3]


def _option_value(parsed: shell_syntax.Command, option: str) -> str:
    arguments = parsed.arguments
    for index, argument in enumerate(arguments[:-1]):
        if argument == option and not parsed.dynamic[index + 1]:
            return arguments[index + 1]
    return ""


def _record_workspace(record: SessionRecord, parsed: shell_syntax.Command, result: dict) -> None:
    workspace, pane = result.get("workspace"), result.get("root_pane")
    if not _valid_entry(workspace, ("workspace_id", "label")) or not _valid_entry(pane, ("cwd", "terminal_id")):
        return
    label = _option_value(parsed, "--label")
    if label and label != workspace["label"]:
        return
    if parsed.arguments[1] == "worktree" and not _valid_entry(result.get("worktree"), ("path",)):
        return
    entry = {
        "path": _normpath(result["worktree"]["path"] if parsed.arguments[1] == "worktree" else pane["cwd"]),
        "label": workspace["label"],
        "terminal_id": pane["terminal_id"],
    }
    _save(record, workspaces={**entries(record, "workspaces"), workspace["workspace_id"]: entry})


def created_result(response: object) -> dict:
    """The `result` object of a command's JSON output; anything failed or malformed gives none."""
    if isinstance(response, dict):
        if response.get("interrupted") or response.get("is_error") or response.get("isError"):
            return {}
        response = response.get("stdout")
    if not isinstance(response, str):
        return {}
    try:
        result = json.loads(response)["result"]
    except TypeError, ValueError, KeyError:
        return {}
    return result if isinstance(result, dict) else {}


def _require_closable(record: SessionRecord, parsed: shell_syntax.Command) -> None:
    """Plain closes only: Herdr itself refuses a primary's close while a linked workspace is open."""
    words = list(zip(parsed.arguments[3:], parsed.dynamic[3:], strict=True))
    options = {word for word, _ in words if word.startswith("-")}
    ids = [word if not dynamic else "" for word, dynamic in words if not word.startswith("-")]
    if options:
        raise ScopeError(f"Herdr workspace close option {min(options)} needs the user's judgment")
    _require_owned_workspace(record, ids[0] if len(ids) == 1 else "")


def _require_removable(record: SessionRecord, parsed: shell_syntax.Command) -> None:
    workspace = _option_value(parsed, "--workspace")
    if not workspace or parsed.arguments[3:] != ("--workspace", workspace):
        raise ScopeError("Herdr worktree remove needs only --workspace ID for automatic approval")
    _require_owned_workspace(record, workspace, removable=True)


def _require_owned_workspace(record: SessionRecord, workspace: str, *, removable: bool = False) -> None:
    """Close only a recorded workspace still holding its root and exclusively recorded agents."""
    entry = entries(record, "workspaces").get(workspace)
    if not entry or not _matches_live(workspace, entry, removable=removable):
        raise ScopeError(f"Herdr workspace {workspace} was not created by this session or no longer matches")
    panes = _live_panes(workspace)
    agents = entries(record, "agents")
    if not any(pane.get("terminal_id") == entry["terminal_id"] for pane in panes) or any(
        not _matches_agent(agent, agents.get(agent.get("name"), {}))
        for agent in _live_agents()
        if agent.get("workspace_id") == workspace
    ):
        raise ScopeError(f"Herdr workspace {workspace} no longer holds only terminals this session created")


def _expire_workspace(record: SessionRecord, workspace: str) -> None:
    _save(
        record,
        workspaces={key: value for key, value in entries(record, "workspaces").items() if key != workspace},
        agents={
            key: value for key, value in entries(record, "agents").items() if value.get("workspace_id") != workspace
        },
    )


def _live_panes(workspace: str) -> list[dict]:
    panes = herdr_result("pane", "list", "--workspace", workspace).get("panes", [])
    return [pane for pane in panes if isinstance(pane, dict)]


def _matches_live(workspace: str, entry: dict[str, str], *, removable: bool = False) -> bool:
    for item in workspace_items():
        if item["workspace_id"] != workspace:
            continue
        worktree = item.get("worktree")
        if removable and not (isinstance(worktree, dict) and worktree.get("is_linked_worktree") is True):
            return False
        return item.get("label") == entry["label"] and live_path(item) == entry["path"]
    return False


def live_path(item: dict) -> str:
    """The workspace's checkout path, or its root pane's directory before a worktree attaches the group."""
    info = item.get("worktree")
    pane = item.get("root_pane")
    candidates = [
        info.get("checkout_path") if isinstance(info, dict) else None,
        pane.get("cwd") if isinstance(pane, dict) else None,
    ]
    return next((_normpath(path) for path in candidates if isinstance(path, str) and path), "")


def _valid_entry(entry: object, keys: tuple[str, ...]) -> TypeGuard[dict]:
    return isinstance(entry, dict) and all(isinstance(entry.get(key), str) and entry[key] for key in keys)


def entries(record: SessionRecord, key: str) -> dict[str, dict]:
    """The session's recorded `agents` or `workspaces` by name or ID, dropping entries that are malformed."""
    path = record.directory / AGENTS_FILE
    value = read_json(path).get(key) if path.exists() else None
    keys = ("terminal_id", "pane_id", "workspace_id", "name") if key == "agents" else ("terminal_id", "path", "label")
    return (
        {name: entry for name, entry in value.items() if _valid_entry(entry, keys)} if isinstance(value, dict) else {}
    )


def _normpath(path: str) -> str:
    return os.path.normpath(path)


def _claim(name: str) -> None:
    if not name:
        raise ScopeError("Herdr agent name is a shell expansion, so this session cannot claim it")
    if name in live_agent_names():
        raise ScopeError(f"Herdr agent {name} already exists and was not started by this session")


def _require_owned(record: SessionRecord, name: str) -> None:
    entry = entries(record, "agents").get(name, {})
    if any(_matches_agent(agent, entry) for agent in _live_agents() if entry):
        return
    shown = name or "chosen at run time"
    raise ScopeError(f"Herdr agent {shown} was not started by this session; its pane may run outside the sandbox")


def _agent_session(agent: dict) -> str:
    session = agent.get("agent_session")
    value = session.get("value") if isinstance(session, dict) else None
    return value if isinstance(value, str) else ""


def _matches_agent(agent: dict, entry: dict) -> bool:
    return (
        agent.get("name") == entry.get("name")
        and agent.get("terminal_id") == entry.get("terminal_id")
        and _agent_session(agent) == _agent_session(entry)
    )


def _save(record: SessionRecord, **values: object) -> None:
    path = record.directory / AGENTS_FILE
    current = read_json(path) if path.exists() else {}
    atomic_json(path, {**current, **values})


def workspace_items() -> list[dict]:
    """Open workspaces."""
    workspaces = herdr_result("workspace", "list").get("workspaces", [])
    return [item for item in workspaces if isinstance(item, dict) and isinstance(item.get("workspace_id"), str)]


def live_agent_names() -> set[str]:
    """Names Herdr already serves; an unreachable Herdr cannot vouch for a name, so the claim asks."""
    return {agent["name"] for agent in _live_agents() if isinstance(agent.get("name"), str) and agent["name"]}


def _live_agents() -> list[dict]:
    agents = herdr_result("agent", "list").get("agents", [])
    return [agent for agent in agents if isinstance(agent, dict)]


def herdr_result(*command: str) -> dict:
    """Read a Herdr listing; an unreachable Herdr cannot vouch for anything, so the check asks."""
    try:
        result = subprocess.run(
            ["herdr", *command], capture_output=True, text=True, check=True, timeout=LIST_TIMEOUT_SECONDS
        )
        value = json.loads(result.stdout)["result"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        raise ScopeError(f"Herdr {' '.join(command)} failed, so ownership cannot be checked") from error
    if not isinstance(value, dict):
        raise ScopeError(f"Herdr {' '.join(command)} returned no result, so ownership cannot be checked")
    return value
