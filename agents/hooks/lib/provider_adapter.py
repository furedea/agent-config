"""Translate provider hook payloads at the boundary to shared hook implementations.

Each provider adapter declares only a Profile of provider facts. Payload normalization,
guard dispatch, and CLI validation live here so the providers cannot drift apart.
"""

import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import audit_log
import guard_command
import guard_file
import guard_git
import guard_suppression
import hook_decision
import hook_dispatch
import hook_input
import lint_format
import patch_input
import secret_path_policy
import shell_paths
import shell_syntax
import verification_session

SECRET_PATH_RULE = "guard_secret_paths.sh"
SHELL_MODES = ("allowed", "forbidden", "git", "commit")
PATH_MODES = ("command", "patch", "read")
AUDIT_KINDS = ("tool", "compaction")
CONTENT_MODES = ("prompt", "read", "write", "apply-patch", "suppression")
NO_ARGUMENT: tuple[str, ...] = ()
ANY_ARGUMENT = None
Formatter = Callable[[str, dict], dict]


def denial(result: dict) -> dict | None:
    """Return the block decision for a Claude-shaped denial or escalation; these providers cannot prompt."""
    specific = result.get("hookSpecificOutput")
    if not isinstance(specific, dict) or specific.get("permissionDecision") not in {"deny", "ask"}:
        return None
    return {"decision": "block", "reason": specific.get("permissionDecisionReason") or "Blocked by hook policy"}


def system_message(_event: str, result: dict) -> dict:
    """Format a shared result for providers that surface a top-level systemMessage."""
    message = result.get("systemMessage")
    return denial(result) or ({"systemMessage": message} if message else result)


def additional_context(event: str, result: dict) -> dict:
    """Format a shared result for providers that surface messages as additionalContext."""
    message = result.get("systemMessage")
    context = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}
    return denial(result) or (context if message else result)


def system_message_output(message: str) -> dict:
    """Encode diagnostics for providers that read a top-level systemMessage."""
    return {"systemMessage": message}


def no_cwd() -> str:
    """Stand in for a working directory when the provider payload carries none, so the process directory is kept."""
    return ""


@dataclass(frozen=True)
class Profile:
    """Provider facts the shared adapter needs; every behavior derived from them is shared.

    `events` maps verification events to native event names and enables `native`.
    `compaction_events` maps native event names to shared audit event names and enables `audit`.
    `manifest_env` names the manifest override and enables `dispatch`.
    """

    name: str
    tools: Mapping[str, str] = field(default_factory=dict)
    events: Mapping[str, str] = field(default_factory=dict)
    compaction_events: Mapping[str, str] = field(default_factory=dict)
    formatter: Formatter = system_message
    lint_output: Callable[[str], dict] = lint_format.context
    content_modes: tuple[str, ...] = CONTENT_MODES
    cwd_fallback: Callable[[], str] = os.getcwd
    manifest_env: str = ""
    manifest_default: str = ""


class Adapter:
    """Run one provider's hook commands against the shared hook implementations."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile

    def main(self, arguments: list[str]) -> int:
        """Run the hook command named by `arguments` and return its exit status.

        Return 1 after printing usage for an unknown command or argument, and 2 when the payload or a guard
        blocks the call.
        """
        kind, rest = (arguments[0], arguments[1:]) if arguments else ("", [])
        if not self._accepts(kind, rest):
            print(f"Usage: hook_adapter.py <{self._usage()}>", file=sys.stderr)
            return 1
        try:
            return self.dispatch(kind, rest, self._payload())
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as error:
            print(f"BLOCKED: {error}", file=sys.stderr)
            return 2

    def dispatch(self, kind: str, arguments: list[str], payload: dict) -> int:
        """Run one already-validated command against `payload`; `arguments` are the choices `kind` takes."""
        if kind == "lint":
            return self.lint(payload)
        if kind == "harness":
            return self._harness(payload)
        commands = {
            "native": self._native,
            "audit": self._audit,
            "dispatch": self._fan_out,
            "shell": self._shell,
            "paths": self._check_paths,
            "content": self._content,
        }
        return commands[kind](arguments[0], payload)

    def normalized(self, payload: dict) -> dict:
        """Copy the provider payload, adding the shared fields and canonical tool name."""
        result = dict(payload)
        result["tool_input"] = tool_input(payload)
        result.setdefault("cwd", self.profile.cwd_fallback())
        result.setdefault("prompt", payload.get("text") or "")
        result["provider"] = self.profile.name
        if canonical := self.profile.tools.get(payload.get("tool_name") or ""):
            result["tool_name"] = canonical
        return result

    def translated(self, payload: dict, tool: str, values: dict) -> dict:
        """Forward only the fields a shared guard reads, under the shared tool name."""
        return {
            "tool_name": tool,
            "tool_input": values,
            "session_id": payload.get("session_id") or "",
            "cwd": payload.get("cwd") or self.profile.cwd_fallback(),
            "provider": self.profile.name,
        }

    def _native(self, event: str, payload: dict) -> int:
        context = self.normalized(payload)
        try:
            result = verification_session.dispatch(self.profile.name, event, context)
        except (OSError, ValueError, TypeError, KeyError) as error:
            result = verification_session.failure(event, context, error)
        output = self.profile.formatter(self.profile.events[event], result)
        print(json.dumps(output, ensure_ascii=True, separators=(",", ":")))
        return 0

    def _audit(self, kind: str, payload: dict) -> int:
        context = self.normalized(payload)
        if kind == "compaction":
            context = self._compaction_context(context)
        if context is not None:
            audit_log.append_record(
                audit_log.record(kind, context, self.profile.name), cwd=Path(context["cwd"] or ".")
            )
        return 0

    def _fan_out(self, event: str, payload: dict) -> int:
        return hook_dispatch.run(self._manifest(), event, payload)

    def _shell(self, mode: str, payload: dict) -> int:
        values = {"command": _command_text(self.normalized(payload)["tool_input"])}
        command = self.translated(payload, "Bash", values)
        if mode == "commit":
            verdict = guard_file.commit_verdict(command, _shared_directory())
        elif mode == "git":
            verdict = guard_git.decide(command)
        else:
            verdict = guard_command.decide(mode, command, _shared_directory())
        return hook_decision.emit(verdict.hardened())

    def lint(self, payload: dict) -> int:
        """Report shared quality diagnostics using the PostToolUse JSON contract."""
        context = self.normalized(payload)
        if not views_only(context) and not failed(context):
            lint_format.emit(lint_format.diagnostics(context), self.profile.lint_output)
        return 0

    def _harness(self, payload: dict) -> int:
        context = self.normalized(payload)
        for name in () if views_only(context) else _edit_targets(context):
            absolute = name if name.startswith(("/", "~/")) else str(Path.cwd() / name)
            values = {"file_path": absolute}
            if status := guard_file.check(
                "harness", self.translated(payload, "apply_patch", values), _shared_directory()
            ):
                return status
        return 0

    def _check_paths(self, mode: str, payload: dict) -> int:
        rules = secret_path_policy.load(_secret_policy_path())
        context = self.normalized(payload)
        try:
            with hook_input.payload_directory(context):
                candidates = (
                    _command_paths(_command_text(context["tool_input"]))
                    if mode == "command"
                    else _edit_targets(context)
                )
        except shell_paths.UnexpandableGlobError as error:
            audit_log.blocked(_secret_path_refusal(mode, "", context))
            return hook_decision.emit(hook_decision.ask(f"Needs review: {error}.").hardened())
        for value in candidates:
            if rule := secret_path_policy.blocked_rule(
                value, rules, editing=mode == "patch" and not views_only(context)
            ):
                audit_log.blocked(_secret_path_refusal(mode, value, context))
                raise ValueError(_secret_path_reason(value, rule))
        return 0

    def _content(self, mode: str, payload: dict) -> int:
        context = self.normalized(payload)
        if mode == "suppression":
            return hook_decision.emit(guard_suppression.decide(context).hardened())
        if mode != "apply-patch":
            return guard_file.check(mode, context, _shared_directory())
        body = hook_input.patch_body(context["tool_input"], context.get("tool_name") or "apply_patch")
        values = {"content": patch_input.added_text(body)}
        return guard_file.check("write", self.translated(payload, "Edit", values), _shared_directory())

    def _compaction_context(self, context: dict) -> dict | None:
        """Name a native compaction event as shared audit expects, or drop an unknown event."""
        event = self.profile.compaction_events.get(context.get("hook_event_name") or "")
        return None if event is None else context | {"hook_event_name": event}

    def _manifest(self) -> Path:
        default = Path.home() / self.profile.manifest_default
        return Path(os.environ.get(self.profile.manifest_env, str(default)))

    def _payload(self) -> dict:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise TypeError("hook payload must be an object")
        cwd = payload.get("cwd") or self.profile.cwd_fallback()
        if isinstance(cwd, str) and cwd:
            os.chdir(cwd)
        return self._in_workdir(payload)

    def _in_workdir(self, payload: dict) -> dict:
        """Move to the directory a shell tool runs its command in, so guards inspect that repository."""
        values = payload.get("tool_input")
        if not isinstance(values, dict):
            return payload
        workdir = values.get("workdir")
        if not isinstance(workdir, str) or not workdir:
            return payload
        os.chdir(workdir)
        # The forwarded cwd is already the workdir; keeping `workdir` would apply a relative one twice.
        resolved = {key: value for key, value in values.items() if key != "workdir"}
        return payload | {"cwd": str(Path.cwd()), "tool_input": resolved}

    def _accepts(self, kind: str, rest: list[str]) -> bool:
        commands = self._commands()
        if kind not in commands or any(value in {"-h", "--help"} for value in rest):
            return False
        choices = commands[kind]
        if choices == NO_ARGUMENT:
            return not rest
        return len(rest) == 1 and (choices is ANY_ARGUMENT or rest[0] in choices)

    def _commands(self) -> dict[str, tuple[str, ...] | None]:
        """Map each accepted command to its argument choices."""
        commands: dict[str, tuple[str, ...] | None] = {}
        if self.profile.events:
            commands["native"] = tuple(self.profile.events)
        if self.profile.compaction_events:
            commands["audit"] = AUDIT_KINDS
        if self.profile.manifest_env:
            commands["dispatch"] = ANY_ARGUMENT
        return commands | {
            "shell": SHELL_MODES,
            "lint": NO_ARGUMENT,
            "harness": NO_ARGUMENT,
            "paths": PATH_MODES,
            "content": self.profile.content_modes,
        }

    def _usage(self) -> str:
        return "|".join(_usage_entry(kind, choices) for kind, choices in self._commands().items())


def _shared_directory() -> Path:
    return Path(os.environ.get("AGENT_HARNESS_ROOT", str(Path.home()))) / ".claude/hooks"


def _secret_policy_path() -> Path:
    default = _shared_directory() / "rules/secret_path_policy.json"
    return Path(os.environ.get("AGENT_SECRET_PATH_POLICY", str(default)))


def tool_input(payload: dict) -> object:
    """Copy the tool arguments; a non-object is kept so the consuming check rejects it."""
    values = payload.get("tool_input")
    if values is None:
        # Hermes carries tool arguments in `args`.
        values = payload.get("args")
    if not isinstance(values, dict):
        return {} if values is None else values
    result = dict(values)
    if name := hook_input.file_path(values):
        result["file_path"] = name
    return result


def views_only(context: dict) -> bool:
    """Tell whether an editor tool call only views a file, so edit-time guards have nothing to check."""
    values = context["tool_input"]
    return context.get("tool_name") == "Edit" and isinstance(values, dict) and values.get("command") == "view"


def failed(context: dict) -> bool:
    """Tell whether the provider reported the tool call as an error, so nothing was edited to check."""
    response = context.get("tool_response")
    return isinstance(response, dict) and response.get("isError") is True


def _command_text(values: dict) -> str:
    return values.get("command") or values.get("cmd") or ""


def _edit_targets(context: dict) -> list[str]:
    values = context["tool_input"]
    body = hook_input.patch_body(values, context.get("tool_name"))
    return [name for name in (hook_input.file_path(values), *patch_input.paths(body)) if name]


def _command_paths(command: str) -> list[str]:
    try:
        return shell_paths.command_paths(command)
    except shell_syntax.UnsupportedSyntaxError as error:
        raise ValueError(f"{error}\n\nCommand: {shell_syntax.command_preview(command)}") from error


def _secret_path_refusal(mode: str, value: str, context: dict) -> audit_log.Refusal:
    command = mode == "command"
    return audit_log.Refusal(
        "Bash" if command else "apply_patch",
        SECRET_PATH_RULE,
        context.get("session_id") or "",
        payload=context,
        targets=() if command else (value,),
    )


def _secret_path_reason(value: str, rule: dict) -> str:
    return f"secret path policy matched.\n\nPath: {value}\nPattern: {rule['pattern']}\n\nWhy:\n  {rule['reason']}"


def _usage_entry(kind: str, choices: tuple[str, ...] | None) -> str:
    if choices is ANY_ARGUMENT:
        return f"{kind} <event>"
    return f"{kind} {'/'.join(choices)}" if choices else kind
