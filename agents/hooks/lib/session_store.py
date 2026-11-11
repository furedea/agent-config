"""Private, bounded verification state keyed by native provider sessions."""

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from session_snapshot import COMMIT_ID, Snapshot, capture, head_commit

SCHEMA = 1
RETENTION_SECONDS = 7 * 24 * 60 * 60
LOG_LIMIT_BYTES = 1024 * 1024
TOTAL_LOG_LIMIT_BYTES = 100 * LOG_LIMIT_BYTES
# SessionStart and Herdr ownership hooks wait 0.5 seconds to absorb brief contention
# without stalling interactive hooks behind long-running verification.
LOCK_WAIT_SECONDS = 0.5
LOCK_RETRY_SECONDS = 0.01


class StateError(ValueError):
    """Verification registration or evidence cannot be trusted."""


class ScopeError(StateError):
    """A tool target lies outside the registered worktree and needs the user's judgment."""


class LockTimeoutError(StateError):
    """Another hook held the state lock past the wait limit."""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One registered provider session: its baseline, receipts, logs, and lock."""

    directory: Path
    root: Path
    provider: str

    @property
    def baseline(self) -> Snapshot:
        """The worktree files captured when the session registered, against which changes are measured."""
        return Snapshot.from_json(read_json(self.directory / "baseline.json")["files"])

    @property
    def head(self) -> str | None:
        """The commit HEAD named when the session registered; None for an older record or an empty repository."""
        value = read_json(self.directory / "baseline.json").get("head")
        return value if isinstance(value, str) and COMMIT_ID.fullmatch(value) else None

    def results(self) -> dict:
        """Read the saved results; raise StateError when they are unreadable or lack a `checks` mapping."""
        value = read_json(self.directory / "results.json")
        if not isinstance(value.get("checks"), dict):
            raise StateError("Invalid check results")
        return value

    def save_results(self, value: dict) -> None:
        """Replace the saved results atomically and delete every log that no receipt references any more."""
        atomic_json(self.directory / "results.json", value)
        retained = {
            Path(receipt["log"]).name
            for receipt in value.get("checks", {}).values()
            if isinstance(receipt, dict) and isinstance(receipt.get("log"), str)
        }
        for path in _log_files(self.directory):
            if path.name not in retained:
                path.unlink(missing_ok=True)

    def touch(self) -> None:
        """Keep active sessions without a parent process or a per-tool snapshot."""
        os.utime(self.directory, None)

    def end(self, *, now: float | None = None) -> None:
        """Mark the session ended at `now` (default: the current time) so pruning can expire it."""
        results = self.results()
        results["ended_at"] = time.time() if now is None else now
        self.save_results(results)

    def write_log(self, check_id: str, output: str) -> Path:
        """Store one check's output and return its path; a rerun overwrites it and only the tail is kept."""
        directory = self.directory / "logs"
        private_directory(directory)
        filename = hashlib.sha256(check_id.encode()).hexdigest()[:24] + ".log"
        data = output.encode("utf-8", errors="replace")
        if len(data) > LOG_LIMIT_BYTES:
            header = b"[earlier output truncated]\n"
            data = header + data[-(LOG_LIMIT_BYTES - len(header)) :]
        path = directory / filename
        _atomic_bytes(path, data)
        return path

    @contextmanager
    def lock(self, *, unbounded: bool = False) -> Generator[None]:
        """Hold the session lock; wait at most LOCK_WAIT_SECONDS (raising LockTimeoutError) unless `unbounded`."""
        with file_lock(self.directory / ".lock", timeout=None if unbounded else LOCK_WAIT_SECONDS):
            yield


def state_directory() -> Path:
    """The root of all verification state; raise StateError when XDG_STATE_HOME is not absolute."""
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))).expanduser()
    if not base.is_absolute():
        raise StateError("XDG_STATE_HOME must be absolute")
    return base / "agent-harness/verification"


def worktree_id(root: Path) -> str:
    """The directory name that groups the state of every session in one worktree, derived from its real path."""
    return hashlib.sha256(os.fsencode(root.resolve())).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class SessionKey:
    """The resolved worktree and provider session one registration belongs to."""

    root: Path
    provider: str
    session_id: str


def session_directory(key: SessionKey) -> Path:
    """Locate the state directory of one session; raise StateError for an unknown provider or invalid session ID."""
    if (
        key.provider not in {"codex", "claude", "devin", "hermes", "pi"}
        or not isinstance(key.session_id, str)
        or not 0 < len(key.session_id) <= 256
    ):
        raise StateError("Missing or invalid provider session ID")
    identity = hashlib.sha256(key.session_id.encode()).hexdigest()[:32]
    return state_directory() / worktree_id(key.root) / f"{key.provider}-{identity}"


def register(root: Path, provider: str, session_id: str) -> SessionRecord:
    """Register once from SessionStart; repeated delivery preserves pending work."""
    return _register(SessionKey(root.resolve(), provider, session_id), resuming=False)


def resume(root: Path, provider: str, session_id: str) -> SessionRecord:
    """Register a resumed session, revalidating everything when its registration expired."""
    return _register(SessionKey(root.resolve(), provider, session_id), resuming=True)


def _register(key: SessionKey, *, resuming: bool) -> SessionRecord:
    base = state_directory()
    if base.resolve().is_relative_to(key.root):
        raise StateError("Verification state must be outside the worktree")
    directory = session_directory(key)
    private_directory(base)
    private_directory(directory.parent)
    with file_lock(directory.parent / ".register.lock", timeout=LOCK_WAIT_SECONDS):
        if not directory.exists() and not directory.is_symlink():
            return _create_record(key, directory, resuming=resuming)
    return reopen(directory)


def _create_record(key: SessionKey, directory: Path, *, resuming: bool) -> SessionRecord:
    baseline = capture(key.root)
    with tempfile.TemporaryDirectory(prefix=".register-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        atomic_json(
            staging / "baseline.json",
            {
                "schema": SCHEMA,
                "root": str(key.root),
                "provider": key.provider,
                "created_at": time.time(),
                "files": baseline.to_json(),
                "head": head_commit(key.root),
            },
        )
        atomic_json(staging / "results.json", {"checks": {}, "session_id": key.session_id, "revalidate_all": resuming})
        _atomic_bytes(staging / ".lock", b"")
        Path(staging).rename(directory)
    return SessionRecord(directory, key.root, key.provider)


def reopen(directory: Path) -> SessionRecord:
    """Reactivate an existing registration without discarding its pending results."""
    record = load(directory)
    try:
        with record.lock():
            results = record.results()
            results.pop("ended_at", None)
            record.save_results(results)
    except LockTimeoutError:
        pass
    record.touch()
    return record


def load(directory: Path) -> SessionRecord:
    """Open an existing registration.

    Raise StateError unless it sits directly in the state directory and has a valid baseline.
    """
    base = state_directory()
    if directory.parent.parent != base or directory.is_symlink() or directory.parent.is_symlink():
        raise StateError("Invalid verification registration path")
    baseline = read_json(directory / "baseline.json")
    root = Path(baseline["root"])
    if baseline.get("schema") != SCHEMA or worktree_id(root) != directory.parent.name:
        raise StateError("Invalid verification baseline")
    try:
        Snapshot.from_json(baseline["files"])
    except (ValueError, TypeError, KeyError) as error:
        raise StateError("Invalid verification baseline files") from error
    return SessionRecord(directory, root, baseline["provider"])


def private_directory(path: Path) -> None:
    """Create `path` with mode 0700; raise StateError when it is a symlink or owned by another user."""
    if path.is_symlink():
        raise StateError(f"State directory is a symlink: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise StateError(f"State directory has a different owner: {path}")
    path.chmod(0o700)


def read_json(path: Path) -> dict:
    """Read a JSON object from a state file; raise StateError for a symlink, unreadable file, or non-object."""
    if path.is_symlink():
        raise StateError(f"State file is a symlink: {path}")
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("Expected an object")
        return value
    except (OSError, ValueError) as error:
        raise StateError(f"Unreadable verification record: {path}") from error


def atomic_json(path: Path, value: dict) -> None:
    """Write `value` as compact ASCII JSON so readers see either the old file or the new one, never a partial write."""
    _atomic_bytes(path, json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())


def _atomic_bytes(path: Path, value: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path, *, blocking: bool = True, timeout: float | None = None) -> Generator[None]:
    """Optionally bound lock acquisition; non-blocking callers can skip busy records."""
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as stream:
        if not blocking:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif timeout is None:
            fcntl.flock(stream, fcntl.LOCK_EX)
        else:
            _acquire_lock(stream.fileno(), path, timeout)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _acquire_lock(descriptor: int, path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise LockTimeoutError(f"Timed out waiting for lock {path}; another hook holds it")
        time.sleep(min(LOCK_RETRY_SECONDS, remaining))


def prune(*, now: float | None = None) -> None:
    """Expire ended or inactive sessions and bound logs without dropping failure status."""
    base = state_directory()
    if not base.exists():
        return
    private_directory(base)
    current = time.time() if now is None else now
    try:
        with file_lock(base / ".gc.lock", blocking=False):
            _prune_records(base, current)
    except BlockingIOError:
        return


def _prune_records(base: Path, now: float) -> None:
    candidates = tuple(base.glob("*/*"))
    for directory in (path for path in candidates if _trusted_record_directory(path)):
        _prune_record(directory, now)
    bound_logs(base)


def _trusted_record_directory(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink() and not path.parent.is_symlink()


def bound_logs(base: Path) -> None:
    """Delete the oldest logs until all sessions fit the shared log budget."""
    logs = [path for directory in record_directories(base) for path in _log_files(directory)]
    total = sum(path.stat().st_size for path in logs)
    for path in sorted(logs, key=lambda value: value.stat().st_mtime_ns):
        if total <= TOTAL_LOG_LIMIT_BYTES:
            break
        total -= path.stat().st_size
        path.unlink(missing_ok=True)


def record_directories(base: Path) -> Iterator[Path]:
    """Yield every session directory under `base`, skipping symlinks and non-directories."""
    worktrees = (worktree for worktree in base.iterdir() if not worktree.is_symlink() and worktree.is_dir())
    for worktree in worktrees:
        yield from (directory for directory in worktree.iterdir() if not directory.is_symlink() and directory.is_dir())


def _log_files(directory: Path) -> tuple[Path, ...]:
    logs = directory / "logs"
    if logs.is_symlink() or not logs.is_dir():
        return ()
    return tuple(path for path in logs.glob("*.log") if not path.is_symlink() and path.is_file())


def _prune_record(directory: Path, now: float) -> None:
    try:
        _remove_if_expired(directory, now)
    except OSError, StateError, KeyError, TypeError:
        return


def _remove_if_expired(directory: Path, now: float) -> None:
    # Stop holds this lock throughout verification; GC must skip it without waiting per record.
    with file_lock(directory / ".lock", blocking=False):
        results = load(directory).results()
        last_seen = results.get("ended_at", directory.stat().st_mtime)
        if now - last_seen > RETENTION_SECONDS:
            shutil.rmtree(directory)
