#!/usr/bin/env -S python3 -IB
"""Translate Antigravity hook payloads at the boundary to shared hook implementations."""

import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()
# Antigravity deploys adapters to ~/.gemini/config/hooks, two levels below ~/.gemini; the shared hooks stay in
# ~/.claude/hooks. The source tree keeps them in agents/hooks.
ROOT = SCRIPT.parents[2]
COMMON = ROOT.parent / ".claude/hooks" if ROOT.name == ".gemini" else ROOT / "hooks"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(COMMON / "lib"))

import provider_adapter

NEW_STRING = "new_string"
REPLACEMENT_CONTENT = "ReplacementContent"
REPLACEMENT_CHUNKS = "ReplacementChunks"
SPECIFIC_OUTPUT = "hookSpecificOutput"
DENY = "deny"
FORCE_ASK = "force_ask"
CONTINUE = "continue"
PRE_TOOL_USE = "PreToolUse"
STOP = "Stop"
SESSION_START = "SessionStart"
ARGUMENTS = {
    "CommandLine": "command",
    "Cwd": "workdir",
    "Path": "file_path",
    "AbsolutePath": "file_path",
    "TargetFile": "file_path",
    "SearchPath": "file_path",
    "SearchDirectory": "file_path",
    "DirectoryPath": "file_path",
    "Content": "content",
    "CodeContent": "content",
    REPLACEMENT_CONTENT: NEW_STRING,
}


def read(payload: dict) -> dict:
    """Give an Antigravity camelCase payload the shared shape; `cwd` is the agent's, not the hook process's."""
    call = payload.get("toolCall")
    call = call if isinstance(call, dict) else {}
    result = {
        "session_id": payload.get("conversationId") or "",
        "cwd": payload.get("cwd") or "",
        "hook_event_name": payload.get("hookEventName") or "",
        "prompt": payload.get("lastUserInput") or "",
        "stop_hook_active": bool(payload.get("continuationActive") or payload.get("continuation_active")),
    }
    if call:
        result["tool_name"] = call.get("name") or ""
        result["tool_input"] = shared_arguments(call.get("args"))
    if payload.get("error"):
        result["tool_response"] = {"isError": True, "error": payload["error"]}
    return result


def shared_arguments(args: object) -> object:
    """Rename the tool arguments the shared guards read; a non-object is kept so the consuming check rejects it.

    Two arguments naming one shared field with different values are ambiguous, and a guard that read only one
    could be bypassed through the other, so they are rejected.
    """
    if not isinstance(args, dict):
        return {} if args is None else args
    renamed: dict = {}
    for key, value in args.items():
        field = ARGUMENTS.get(key, key)
        if field in renamed and renamed[field] != value:
            raise ValueError(f"ambiguous tool arguments for {field}: {key}")
        renamed[field] = value
    chunks = args.get(REPLACEMENT_CHUNKS)
    if isinstance(chunks, list):
        renamed[NEW_STRING] = renamed.get(NEW_STRING, "") + "".join(
            chunk[REPLACEMENT_CONTENT]
            for chunk in chunks
            if isinstance(chunk, dict) and isinstance(chunk.get(REPLACEMENT_CONTENT), str)
        )
    return renamed


def no_diagnostics(_message: str) -> dict:
    """PostToolUse takes only `{}`, so lint findings have no channel to the agent."""
    return {}


def review(reason: str) -> dict:
    """Ask on every call: `ask` would let a cached Always Allow bypass the guard."""
    return {"decision": FORCE_ASK, "reason": reason}


def refusal(reason: str) -> dict:
    """Hard-block the tool call; unlike `force_ask`, no cached permission can override it."""
    return {"decision": DENY, "reason": reason}


def output(event: str, result: dict) -> dict:
    """Encode a shared result in the object Antigravity reads for `event`; `{}` lets the call or stop proceed."""
    if event == PRE_TOOL_USE:
        return pre_tool_use(result)
    if event == STOP:
        return (
            {"decision": CONTINUE, "reason": result.get("reason") or "Blocked by hook policy"}
            if result.get("decision") == "block"
            else {}
        )
    if event == SESSION_START:
        context = (result.get(SPECIFIC_OUTPUT) or {}).get("additionalContext")
        return {"injectSteps": [{"systemMessage": {"systemMessage": context}}]} if context else {}
    return {}


def pre_tool_use(result: dict) -> dict:
    """Encode a shared deny or ask as the PreToolUse decision; anything else lets Antigravity decide."""
    specific = result.get(SPECIFIC_OUTPUT)
    decision = specific.get("permissionDecision") if isinstance(specific, dict) else None
    reason = (specific or {}).get("permissionDecisionReason") or "Blocked by hook policy"
    if decision == "ask":
        return review(reason)
    return refusal(reason) if decision == DENY else {}


ADAPTER = provider_adapter.Adapter(
    provider_adapter.Profile(
        name="antigravity",
        tools={
            "run_command": "Bash",
            "read_file": "Read",
            "view_file": "Read",
            "write_file": "Write",
            "write_to_file": "Write",
            "edit_file": "Edit",
            "replace_file_content": "Edit",
            "multi_replace_file_content": "Edit",
            "search_web": "WebSearch",
            "read_url_content": "WebFetch",
        },
        events={
            "session-start": SESSION_START,
            "pre-tool-use": PRE_TOOL_USE,
            "post-tool-use": "PostToolUse",
            "stop": STOP,
        },
        compaction_events={SESSION_START: SESSION_START},
        formatter=output,
        lint_output=no_diagnostics,
        lint_block=no_diagnostics,
        cwd_fallback=provider_adapter.no_cwd,
        reader=read,
        denial=refusal,
        escalation=review,
    )
)


if __name__ == "__main__":
    sys.exit(ADAPTER.main(sys.argv[1:]))
