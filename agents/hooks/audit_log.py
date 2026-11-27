#!/usr/bin/env -S python3 -IB
"""Record guard refusals and approval denials without retaining prompts, commands, or file bodies.

Session content and tool activity belong to atuin threads; compaction details to Claude Code's transcript (ADR-0029).
"""

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent / "lib"))

from session_store import file_lock, private_directory, worktree_id

RETENTION_SECONDS = 7 * 24 * 60 * 60
LOG_LIMIT_BYTES = 1024 * 1024
TOTAL_LOG_LIMIT_BYTES = 100 * LOG_LIMIT_BYTES
CLEANUP_INTERVAL_SECONDS = 60 * 60
MAX_TARGETS = 32
MAX_TARGET_LENGTH = 256
KNOWN_PROVIDERS = frozenset({"antigravity", "claude", "codex", "devin", "dsh", "hermes", "pi"})
CLI_PROVIDERS = frozenset({"claude", "codex", "devin", "hermes", "pi"})
SAFE_LABEL = re.compile(r"[^A-Za-z0-9_.:-]+")


def _label(value: object, fallback: str = "unknown") -> str:
    if not isinstance(value, str) or not value:
        return fallback
    label = SAFE_LABEL.sub("_", value)[:64]
    return label or fallback


def _provider(payload: dict, explicit: str | None = None) -> str:
    candidate = explicit or payload.get("provider")
    if candidate in KNOWN_PROVIDERS:
        return candidate
    return "codex" if payload.get("turn_id") else "claude"


def _session(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _cwd(payload: dict) -> Path:
    value = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    if not isinstance(value, str) or not value:
        return Path.cwd().resolve()
    try:
        return Path(value).expanduser().resolve()
    except OSError, RuntimeError:
        return Path.cwd().resolve()


def _worktree(cwd: Path) -> str:
    try:
        return worktree_id(cwd)
    except OSError, RuntimeError, ValueError:
        return hashlib.sha256(os.fsencode(str(cwd))).hexdigest()[:32]


def _target(value: object, cwd: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if "://" in value or value.startswith(("data:", "mailto:")):
        return "external"
    try:
        path = Path(value).expanduser()
        resolved = (path if path.is_absolute() else cwd / path).resolve()
        relative = resolved.relative_to(cwd)
        result = relative.as_posix()
    except OSError, RuntimeError, ValueError:
        result = f"outside/{Path(value).name or 'unknown'}"
    return result[:MAX_TARGET_LENGTH]


def record(payload: dict, provider: str | None = None) -> dict | None:
    """Produce a metadata-only record of one approval denial."""
    if not isinstance(payload, dict):
        return None
    cwd = _cwd(payload)
    return {
        "event": _label(payload.get("hook_event_name") or "PermissionDenied"),
        "status": "denied",
        "provider": _provider(payload, provider),
        "session": _session(payload.get("session_id")),
        "worktree": _worktree(cwd),
        "tool": _label(payload.get("tool_name"), ""),
        "targets": [],
    }


def _state_root(cwd: Path) -> Path | None:
    base_value = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state")
    try:
        base = Path(base_value).expanduser()
        if not base.is_absolute():
            return None
        if _contains_symlink(base):
            return None
        base = base.resolve()
        if base == cwd or base.is_relative_to(cwd):
            return None
        return base / "agent-harness/audit"
    except OSError, RuntimeError, ValueError:
        return None


def _contains_symlink(path: Path) -> bool:
    """Reject a state path whose existing components could redirect an audit write."""
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        if current.is_symlink():
            return True
    return False


def _files(root: Path) -> list[Path]:
    result: list[Path] = []
    try:
        worktrees = tuple(path for path in root.iterdir() if path.is_dir() and not path.is_symlink())
        providers = tuple(
            provider
            for worktree in worktrees
            for provider in worktree.iterdir()
            if provider.is_dir() and not provider.is_symlink()
        )
        for provider in providers:
            result.extend(path for path in provider.glob("*.jsonl") if not path.is_symlink() and path.is_file())
    except OSError:
        return result
    return result


def _cleanup(root: Path, now: float) -> None:
    stamp = root / ".cleanup"
    try:
        if stamp.exists() and now - stamp.stat().st_mtime < CLEANUP_INTERVAL_SECONDS:
            return
        if stamp.is_symlink():
            return
        descriptor = os.open(stamp, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        os.utime(stamp, (now, now))
        _remove_expired(_files(root), now)
        _remove_oldest_over_limit(_files(root))
    except OSError, ValueError:
        return


def _remove_expired(files: list[Path], now: float) -> None:
    for path in files:
        if now - path.stat().st_mtime > RETENTION_SECONDS:
            path.unlink(missing_ok=True)


def _remove_oldest_over_limit(files: list[Path]) -> None:
    total = sum(path.stat().st_size for path in files)
    for path in sorted(files, key=lambda item: item.stat().st_mtime_ns):
        if total <= TOTAL_LOG_LIMIT_BYTES:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)


def prune(*, now: float | None = None) -> None:
    """Apply retention and total-size limits without affecting enforcement."""
    root = _state_root(Path.cwd().resolve())
    if root is None or not root.exists():
        return
    current = time.time() if now is None else now
    try:
        if _contains_symlink(root):
            return
        private_directory(root)
        with file_lock(root / ".lock"):
            _cleanup(root, current)
    except OSError, ValueError:
        return


def _append_path(directory: Path, stem: str, size: int) -> Path | None:
    for sequence in range(10000):
        path = directory / (f"{stem}.jsonl" if sequence == 0 else f"{stem}.{sequence}.jsonl")
        if not path.is_symlink() and _has_room(path, size):
            return path
    return None


def _has_room(path: Path, size: int) -> bool:
    try:
        return path.stat().st_size + size <= LOG_LIMIT_BYTES
    except FileNotFoundError:
        return True


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if not written:
            raise OSError("audit log write made no progress")
        view = view[written:]


def append_record(entry: dict | None, *, cwd: Path | None = None) -> None:
    """Append one locked JSONL record; observation failures never block work."""
    if not isinstance(entry, dict):
        return
    current = datetime.now(UTC)
    root = _state_root(cwd.resolve() if cwd is not None else Path.cwd().resolve())
    if root is None or _contains_symlink(root):
        return
    record_value = dict(entry, ts=current.strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        _append_locked(root, record_value, current)
    except OSError, ValueError, TypeError:
        return


def _append_locked(root: Path, record_value: dict, current: datetime) -> None:
    encoded = (json.dumps(record_value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(encoded) > LOG_LIMIT_BYTES:
        return
    private_directory(root)
    with file_lock(root / ".lock"):
        directory = _log_directory(root, record_value)
        stem = f"{_label(record_value.get('session'))}-{current:%Y%m%d}"
        path = None if directory is None else _append_path(directory, stem, len(encoded))
        if path is None:
            return
        _append_bytes(path, encoded)
        _cleanup(root, current.timestamp())


def _log_directory(root: Path, record_value: dict) -> Path | None:
    provider = _label(record_value.get("provider"))
    worktree = record_value.get("worktree")
    if not isinstance(worktree, str) or not re.fullmatch(r"[0-9a-f]{32}", worktree):
        worktree = "unknown"
    directory = root / worktree / provider
    if _contains_symlink(directory):
        return None
    private_directory(directory)
    return directory


def _append_bytes(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        _write_all(descriptor, data)
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class Refusal:
    """A guard's refusal, holding only what an audit row may keep or derive."""

    tool: str
    hook: str = ""
    session: str = ""
    payload: dict | None = None
    provider: str | None = None
    targets: tuple[str, ...] = ()
    detail: str = ""


def blocked(refusal: Refusal) -> None:
    """Record a denial; the refusal carries no command or reason text to log."""
    _refusal("Blocked", "blocked", refusal)


def escalated(refusal: Refusal) -> None:
    """Record that a call was handed to the user, keeping only a short label such as the governed prefix."""
    _refusal("Escalated", "asked", refusal)


def _refusal(event: str, status: str, refusal: Refusal) -> None:
    context = dict(refusal.payload) if isinstance(refusal.payload, dict) else {}
    context.setdefault("tool_name", refusal.tool)
    context.setdefault("session_id", refusal.session)
    try:
        entry = record(context, refusal.provider)
    except OSError, RuntimeError, TypeError, ValueError:
        return
    if entry is None:
        return
    entry["event"] = event
    entry["status"] = status
    entry["rule"] = _label(refusal.hook)
    if refusal.detail:
        entry["detail"] = _label(refusal.detail)
    if refusal.targets:
        cwd = _cwd(context)
        entry["targets"] = [target for value in refusal.targets if (target := _target(value, cwd)) is not None][
            :MAX_TARGETS
        ]
    append_record(entry, cwd=_cwd(context))


def main(arguments: list[str]) -> int:
    """Read a denial event without making logging an enforcement gate."""
    if (
        len(arguments) not in {1, 2}
        or arguments[0] != "denied"
        or (len(arguments) == 2 and arguments[1] not in CLI_PROVIDERS)
    ):
        print("Usage: audit_log.py denied [claude|codex|devin|hermes|pi]", file=sys.stderr)
        return 1
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        append_record(record(payload, arguments[1] if len(arguments) == 2 else None), cwd=_cwd(payload))
    except ValueError, TypeError, AttributeError, OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
