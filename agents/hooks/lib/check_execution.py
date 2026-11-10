"""Execute bounded checks in the registered worktree and retain a bounded output tail."""

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from check_evidence import first_error, summarize
from check_selection import Invocation
from dev_shell import EntryFailure, Launch, MissingTool, ProcessEnd, plan_launch

OUTPUT_LIMIT_BYTES = 1024 * 1024


class Status(StrEnum):
    """How one check ended; only the failing statuses block a stop."""

    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"
    MISSING_TOOL = "missing_tool"
    DEV_SHELL_FAILED = "dev_shell_failed"

    @property
    def failing(self) -> bool:
        """Whether the status is evidence against the code.

        A missing tool is neither a pass nor a failure: nothing ran, so the code was not judged.
        """
        return self not in {Status.PASSED, Status.SKIPPED, Status.MISSING_TOOL}

    @property
    def retried(self) -> bool:
        """Whether a saved receipt is rerun on every verification instead of reused.

        The cause (a cold dev shell, a transient nix error, a tool installed since) may clear on its own, and nix
        fails fast when the flake is really broken, so rerunning costs little and never freezes a stale outcome.
        """
        return self in {Status.MISSING_TOOL, Status.DEV_SHELL_FAILED}


@dataclass(frozen=True, slots=True)
class Result:
    """A check's status with the one-line summary to show and the retained output tail."""

    status: Status
    summary: str
    output: str = ""

    @property
    def failed(self) -> bool:
        """Whether the result is evidence against the code and must block a stop."""
        return self.status.failing


def execute(invocation: Invocation, root: Path, budget: float) -> Result:
    """Run one check in `root` for at most `budget` seconds and classify how it ended.

    A tool missing from the agent PATH runs in the project's flake dev shell when it has one, and an absent tool is
    reported as MISSING_TOOL instead of a failure. A process group prevents timeout survivors from changing a later
    snapshot.
    """
    started = time.monotonic()
    launch = plan_launch(invocation.arguments, root, os.environ.get("PATH"))
    if isinstance(launch, MissingTool):
        return _missing_tool(invocation, launch)
    try:
        end = _run(_Process.prepare(invocation, launch, root), budget)
    except OSError as error:
        return Result(Status.UNAVAILABLE, f"{invocation.label}: unavailable · {error}", str(error))
    diagnosis = launch.diagnose(end)
    if isinstance(diagnosis, MissingTool):
        return _missing_tool(invocation, diagnosis)
    output = end.output
    status = Status.TIMEOUT if end.timed_out else Status.FAILED if end.returncode else Status.PASSED
    if isinstance(diagnosis, EntryFailure):
        status = Status.DEV_SHELL_FAILED
    evidence = summarize(invocation.label, output)
    if status == Status.PASSED and evidence.executed == 0:
        related_empty = invocation.label == "vitest" and invocation.scope.endswith(" changed files")
        status = Status.SKIPPED if related_empty and "No test files found" in output else Status.UNAVAILABLE
        output = "No tests executed; selected tests were absent or all skipped.\n" + output
    if status == Status.TIMEOUT:
        output = f"timed out after {budget:g}s\n" + output
    summary = (
        f"{invocation.label}: {evidence.summary} · {invocation.scope} · {status} · {time.monotonic() - started:.1f}s"
    )
    if status.failing:
        summary += f"\nError: {first_error(output)}"
    return Result(status, summary, output)


def _missing_tool(invocation: Invocation, missing: MissingTool) -> Result:
    return Result(Status.MISSING_TOOL, f"{invocation.label}: unavailable · {missing.reason}", missing.reason)


@dataclass(frozen=True, slots=True)
class _Process:
    """The command line, working directory, and environment one check starts with."""

    arguments: tuple[str, ...]
    root: Path
    environment: dict[str, str]

    @classmethod
    def prepare(cls, invocation: Invocation, launch: Launch, root: Path) -> _Process:
        environment = dict(os.environ)
        if invocation.label not in {"bats", "pytest", "rust"}:
            environment["CI"] = "1"
        return cls(launch.arguments, root, environment)


def _run(process: _Process, budget: float) -> ProcessEnd:
    with subprocess.Popen(
        process.arguments,
        cwd=process.root,
        env=process.environment,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as running:
        return _collect(running, max(0.01, budget))


def _collect(process: subprocess.Popen[bytes], budget: float) -> ProcessEnd:
    tail = bytearray()
    truncated = False
    assert process.stdout is not None
    stream = process.stdout

    def drain() -> None:
        nonlocal truncated
        while chunk := os.read(stream.fileno(), 65536):
            tail.extend(chunk)
            if len(tail) > OUTPUT_LIMIT_BYTES:
                del tail[:-OUTPUT_LIMIT_BYTES]
                truncated = True

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=budget)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        reader.join(timeout=2)
    return ProcessEnd(process.returncode, tail.decode("utf-8", errors="replace"), timed_out, truncated)
