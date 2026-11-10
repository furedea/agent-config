"""Decide whether a verification tool runs from the agent PATH, in the flake dev shell, or not at all."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

COMMAND_NOT_FOUND_EXIT = 127
_DEV_SHELL_OUTPUT = re.compile(r"\bdevShells?\b")
_NOT_FOUND_MARKER = "dev-shell-tool-not-found:"
# The probe tells a tool the dev shell lacks apart from a test run that itself fails.
_PROBE = (
    f'command -v "$1" >/dev/null 2>&1 || {{ echo "{_NOT_FOUND_MARKER} $1" >&2; exit {COMMAND_NOT_FOUND_EXIT}; }}; '
    'exec "$@"'
)


@dataclass(frozen=True, slots=True)
class Launch:
    """The argument vector to start, and whether it enters the flake dev shell."""

    arguments: tuple[str, ...]
    via_dev_shell: bool

    def tool_missing(self, returncode: int, output: str) -> bool:
        """Whether the dev shell started but did not provide the tool, as opposed to the tool itself failing."""
        return self.via_dev_shell and returncode == COMMAND_NOT_FOUND_EXIT and _NOT_FOUND_MARKER in output


@dataclass(frozen=True, slots=True)
class MissingTool:
    """No PATH entry and no dev shell provides the tool; the reason names what was tried."""

    reason: str


def plan_launch(arguments: tuple[str, ...], root: Path, search_path: str | None) -> Launch | MissingTool:
    """Prefer the agent PATH so projects that already resolve their tools there run unchanged.

    The dev shell is used only when the tool is absent from `search_path` and `root/flake.nix` declares a dev shell.
    Detection reads flake.nix text instead of evaluating the flake, so it costs no Nix evaluation.
    """
    tool = arguments[0]
    if shutil.which(tool, path=search_path):
        return Launch(arguments, via_dev_shell=False)
    if not _declares_dev_shell(root):
        return MissingTool(f"{tool} not found on PATH and the project has no flake dev shell")
    if not shutil.which("nix", path=search_path):
        return MissingTool(f"{tool} not found on PATH; the project has a flake dev shell but nix is not on PATH")
    return Launch(("nix", "develop", "--command", "sh", "-c", _PROBE, "sh", *arguments), via_dev_shell=True)


def missing_in_dev_shell(tool: str) -> MissingTool:
    """Describe a tool the project's dev shell was entered for but did not provide."""
    return MissingTool(f"{tool} not found on PATH or in the flake dev shell")


def _declares_dev_shell(root: Path) -> bool:
    try:
        return bool(_DEV_SHELL_OUTPUT.search((root / "flake.nix").read_text()))
    except OSError:
        return False
