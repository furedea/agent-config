"""Decide whether a verification tool runs from the agent PATH, in the flake dev shell, or not at all."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

COMMAND_NOT_FOUND_EXIT = 127
_DEV_SHELL_OUTPUT = re.compile(r"\bdevShells?\b")
_ENTERED_MARKER = "dev-shell-entered"
_NOT_FOUND_MARKER = "dev-shell-tool-not-found:"
# The probe separates three endings: nix never reached the command (no entered marker), the dev shell lacks the
# tool (not-found marker and exit 127), and the tool itself ran and failed.
_PROBE = (
    f'echo "{_ENTERED_MARKER}" >&2; '
    f'command -v "$1" >/dev/null 2>&1 || {{ echo "{_NOT_FOUND_MARKER} $1" >&2; exit {COMMAND_NOT_FOUND_EXIT}; }}; '
    'exec "$@"'
)


@dataclass(frozen=True, slots=True)
class ProcessEnd:
    """How a launched process ended, as far as the retained output tail shows."""

    returncode: int
    output: str
    timed_out: bool
    truncated: bool


@dataclass(frozen=True, slots=True)
class MissingTool:
    """No PATH entry and no dev shell provides the tool; the reason names what was tried."""

    reason: str


@dataclass(frozen=True, slots=True)
class EntryFailure:
    """Nix exited before the dev shell started, so no test ran; nix's own output explains why."""


@dataclass(frozen=True, slots=True)
class Launch:
    """The tool a check needs, the argument vector that starts it, and whether that enters the flake dev shell."""

    tool: str
    arguments: tuple[str, ...]
    via_dev_shell: bool

    def diagnose(self, end: ProcessEnd) -> MissingTool | EntryFailure | None:
        """Tell an environment problem from a code result: None means the outcome stands and is judged as usual.

        A project that declares a dev shell is expected to enter it, so nix exiting before the shell starts
        (evaluation or build error, for example in a flake.nix edited this session) is an EntryFailure: a failure,
        with nix's output as the log. Two endings are not judged on the code: the budget spent before the shell
        started, and a working shell that lacks the tool (both MissingTool).
        """
        if not self.via_dev_shell:
            return None
        if _ENTERED_MARKER not in end.output:
            # A truncated tail may have dropped the marker, which proves the shell started.
            if end.truncated:
                return None
            if end.timed_out:
                return MissingTool("the flake dev shell did not start within the check budget")
            return EntryFailure() if end.returncode else None
        if end.returncode == COMMAND_NOT_FOUND_EXIT and _NOT_FOUND_MARKER in end.output:
            return MissingTool(f"{self.tool} not found on PATH or in the flake dev shell")
        return None


def plan_launch(arguments: tuple[str, ...], root: Path, search_path: str | None) -> Launch | MissingTool:
    """Prefer the agent PATH so projects that already resolve their tools there run unchanged.

    The dev shell is used only when the tool is absent from `search_path` and `root/flake.nix` declares a dev shell.
    Detection reads flake.nix text instead of evaluating the flake, so it costs no Nix evaluation.
    """
    tool = arguments[0]
    if shutil.which(tool, path=search_path):
        return Launch(tool, arguments, via_dev_shell=False)
    if not _declares_dev_shell(root):
        return MissingTool(f"{tool} not found on PATH and the project has no flake dev shell")
    if not shutil.which("nix", path=search_path):
        return MissingTool(f"{tool} not found on PATH; the project has a flake dev shell but nix is not on PATH")
    # --no-write-lock-file keeps the verified worktree read-only: nix would otherwise create or refresh flake.lock.
    entered = ("nix", "develop", "--no-write-lock-file", "--command", "sh", "-c", _PROBE, "sh", *arguments)
    return Launch(tool, entered, via_dev_shell=True)


def _declares_dev_shell(root: Path) -> bool:
    try:
        return bool(_DEV_SHELL_OUTPUT.search((root / "flake.nix").read_text()))
    except OSError:
        return False
