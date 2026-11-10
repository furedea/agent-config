"""Find the Herdr workspaces of a primary checkout that an agent created and nothing occupies."""

from pathlib import Path

import herdr_ownership
import session_store


def idle_primary_workspaces(primary: Path) -> list[str]:
    """Return the ids of workspaces that may be closed for the primary checkout `primary`.

    A workspace qualifies only when a registered agent session recorded creating it, its live label and path still
    match that record, its recorded terminal is still present, and no live agent runs in it. Missing or malformed
    Herdr state proves nothing idle: ValueError is raised for an invalid listing, and OSError or
    subprocess.SubprocessError propagate from the Herdr call.
    """
    owned = _recorded_primary_workspaces(primary)
    if not owned:
        return []
    identities = []
    for workspace in _herdr_items("workspace"):
        identity = workspace.get("workspace_id")
        if not isinstance(identity, str) or not identity:
            continue
        entry = owned.get(identity)
        if (
            not entry
            or workspace.get("label") != entry["label"]
            or herdr_ownership.live_path(workspace) != str(primary)
        ):
            continue
        if _is_idle(identity, entry):
            identities.append(identity)
    return identities


def _recorded_primary_workspaces(primary: Path) -> dict[str, dict]:
    """Find primary workspaces created by any registered agent session."""
    base = session_store.state_directory()
    if not base.is_dir():
        return {}
    workspaces = {}
    for directory in session_store.record_directories(base):
        try:
            record = session_store.load(directory)
            owned = herdr_ownership.entries(record, "workspaces")
        except OSError, ValueError, KeyError, TypeError:
            continue
        workspaces.update({key: entry for key, entry in owned.items() if Path(entry["path"]).resolve() == primary})
    return workspaces


def _is_idle(identity: str, entry: dict) -> bool:
    panes = _herdr_items("pane", "--workspace", identity)
    if not any(pane.get("terminal_id") == entry["terminal_id"] for pane in panes):
        return False
    terminals = {pane["terminal_id"] for pane in panes if pane.get("terminal_id")}
    pane_ids = {pane["pane_id"] for pane in panes if pane.get("pane_id")}
    return not any(
        agent.get("workspace_id") == identity
        or agent.get("terminal_id") in terminals
        or (not agent.get("workspace_id") and agent.get("pane_id") in pane_ids)
        for agent in _herdr_items("agent")
    )


def _herdr_items(kind: str, *arguments: str) -> list[dict]:
    """Require an explicit listing; missing or malformed live state cannot prove a workspace idle."""
    items = herdr_ownership.herdr_result(kind, "list", *arguments).get(kind + "s")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError(f"Invalid Herdr {kind} listing")
    return items
