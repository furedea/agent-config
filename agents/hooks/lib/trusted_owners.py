"""Decide whether a project's allow rules come from an owner this machine trusts.

The owner is read from the repository's `origin` URL, never from where the checkout sits on disk.
Anything that cannot be established, such as a missing origin or an unreachable GitHub, is not trusted.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


LOOKUP_TIMEOUT_SECONDS = 5
ORIGIN_URL = re.compile(
    r"(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9_][A-Za-z0-9._-]*?)(?:\.git)?/?"
)
CONFIG_KEYS = {"owners", "exclude_forks"}


@dataclass(frozen=True, slots=True)
class TrustedOwners:
    owners: frozenset[str]
    exclude_forks: bool


@dataclass(frozen=True, slots=True)
class Ignored:
    """Project allow rules left out, with the project they belong to and what to tell the user."""

    root: Path
    message: str


def load(path: Path) -> TrustedOwners:
    """Validate the trusted owner list at its boundary, so a malformed file never widens trust."""
    try:
        data = json.loads(path.read_text())
        owners = data["owners"]
        if set(data) != CONFIG_KEYS or type(data["exclude_forks"]) is not bool:
            raise ValueError("invalid keys")
        if not isinstance(owners, list) or not owners or not all(isinstance(item, str) and item for item in owners):
            raise ValueError("invalid owners")
        return TrustedOwners(frozenset(owner.lower() for owner in owners), data["exclude_forks"])
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError(f"invalid trusted owners: {path}") from error


def parse_origin(url: str) -> tuple[str, str] | None:
    """The GitHub owner and repository an origin URL names; any other host is unknown."""
    match = ORIGIN_URL.fullmatch(url.strip())
    return (match["owner"], match["repo"]) if match else None


def ignored_rules(root: Path, trusted: TrustedOwners) -> Ignored | None:
    """None when the project's allow rules may apply, otherwise why they are left out."""
    reason = distrust_reason(root, trusted)
    if not reason:
        return None
    return Ignored(
        root,
        f"Project allow rules are ignored ({reason}). Only repositories of owners listed in trusted_owners.json "
        "in agent-config count, forks excluded; add the owner there to apply them.",
    )


def announce_once(ignored: Ignored) -> bool:
    """Whether to tell the user now; the project is remembered so the notice is shown only once."""
    marker = state_directory() / "announced" / hashlib.sha256(os.fsencode(ignored.root.resolve())).hexdigest()[:32]
    if marker.exists():
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except OSError:
        pass
    return True


def distrust_reason(root: Path, trusted: TrustedOwners) -> str:
    """Empty when the origin's owner is listed and, if forks are excluded, the repository is not one."""
    repository = origin_repository(root)
    if repository is None:
        return "no GitHub origin to take an owner from"
    owner, name = repository
    if owner.lower() not in trusted.owners:
        return f"owner '{owner}' is not trusted"
    if not trusted.exclude_forks:
        return ""
    fork = is_fork(owner, name)
    if fork is None:
        return f"cannot tell whether {owner}/{name} is a fork"
    return f"{owner}/{name} is a fork" if fork else ""


def origin_repository(root: Path) -> tuple[str, str] | None:
    try:
        url = subprocess.check_output(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return parse_origin(url)


def is_fork(owner: str, name: str) -> bool | None:
    """Ask GitHub once per repository and remember a clear answer; None when it cannot be established."""
    cache = state_directory() / "forks" / f"{owner.lower()}__{name.lower()}"
    answer = cached_answer(cache) or github_answer(owner, name)
    if answer is None:
        return None
    remember(cache, answer)
    return answer == "true"


def cached_answer(cache: Path) -> str | None:
    try:
        answer = cache.read_text().strip()
    except OSError:
        return None
    return answer if answer in {"true", "false"} else None


def github_answer(owner: str, name: str) -> str | None:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{name}", "--jq", ".fork"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=True,
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    answer = result.stdout.strip()
    return answer if answer in {"true", "false"} else None


def remember(cache: Path, answer: str) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(answer)
    except OSError:
        pass


def state_directory() -> Path:
    """The hooks' state directory; a relative XDG_STATE_HOME would land inside the project, so it is not used."""
    configured = Path(os.environ.get("XDG_STATE_HOME", "")).expanduser()
    base = configured if configured.is_absolute() else Path.home() / ".local/state"
    return base / "agent-harness/trusted-owners"
