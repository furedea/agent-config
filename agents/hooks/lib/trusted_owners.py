"""Decide whether a project's allow rules come from an owner this machine trusts.

The owner is read from the repository's `origin` URL, never from where the checkout sits on disk.
Anything that cannot be established, such as a missing origin or an unreachable GitHub, is not trusted.

A repository named in the `repositories` list of the trusted owners file is one a person verified is not a fork:
it is answered at once, with no lookup (hosts without `gh` or credentials, and private repositories, rely on it).
Any other repository is asked of, in order: the remembered answer, `gh`, and the unauthenticated public GitHub API.
"""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request


LOOKUP_TIMEOUT_SECONDS = 5
PUBLIC_API = "https://api.github.com/repos/{owner}/{name}"
PUBLIC_API_MAX_BYTES = 1_000_000
ORIGIN_URL = re.compile(
    r"(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9_][A-Za-z0-9._-]*?)(?:\.git)?/?"
)
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_][A-Za-z0-9._-]*")
REQUIRED_KEYS = {"owners", "exclude_forks"}
CONFIG_KEYS = REQUIRED_KEYS | {"repositories"}
FIX_OWNER = (
    "Only repositories of owners listed in trusted_owners.json in agent-config count, forks excluded; "
    "add the owner there to apply them."
)


@dataclass(frozen=True, slots=True)
class TrustedOwners:
    owners: frozenset[str]
    exclude_forks: bool
    repositories: frozenset[str] = frozenset()

    def declares(self, owner: str, name: str) -> bool:
        return f"{owner}/{name}".lower() in self.repositories


@dataclass(frozen=True, slots=True)
class Distrust:
    """Why a project is not trusted and how to change that."""

    reason: str
    fix: str


@dataclass(frozen=True, slots=True)
class NoAnswer:
    """No source could say whether a repository is a fork; `failures` names what each one lacked."""

    failures: tuple[str, ...]


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
        repositories = data.get("repositories", [])
        if not REQUIRED_KEYS <= set(data) <= CONFIG_KEYS or type(data["exclude_forks"]) is not bool:
            raise ValueError("invalid keys")
        if not isinstance(owners, list) or not owners or not all(isinstance(item, str) and item for item in owners):
            raise ValueError("invalid owners")
        if not isinstance(repositories, list) or not all(
            isinstance(item, str) and REPOSITORY_NAME.fullmatch(item) for item in repositories
        ):
            raise ValueError("invalid repositories")
        return TrustedOwners(
            frozenset(owner.lower() for owner in owners),
            data["exclude_forks"],
            frozenset(repository.lower() for repository in repositories),
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError(f"invalid trusted owners: {path}") from error


def parse_origin(url: str) -> tuple[str, str] | None:
    """The GitHub owner and repository an origin URL names; any other host is unknown."""
    match = ORIGIN_URL.fullmatch(url.strip())
    return (match["owner"], match["repo"]) if match else None


def ignored_rules(root: Path, trusted: TrustedOwners) -> Ignored | None:
    """None when the project's allow rules may apply, otherwise why they are left out."""
    distrust = distrust_reason(root, trusted)
    if distrust is None:
        return None
    return Ignored(root, f"Project allow rules are ignored ({distrust.reason}). {distrust.fix}")


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


def distrust_reason(root: Path, trusted: TrustedOwners) -> Distrust | None:
    """None when the origin's owner is listed and, if forks are excluded, the repository is not one."""
    repository = origin_repository(root)
    if repository is None:
        return Distrust("no GitHub origin to take an owner from", FIX_OWNER)
    owner, name = repository
    if owner.lower() not in trusted.owners:
        return Distrust(f"owner '{owner}' is not trusted", FIX_OWNER)
    if not trusted.exclude_forks:
        return None
    fork = is_fork(owner, name, trusted)
    if isinstance(fork, NoAnswer):
        return Distrust(
            f"cannot tell whether {owner}/{name} is a fork: {'; '.join(fork.failures)}",
            f'Once you have verified it is not a fork, add "{owner}/{name}" to "repositories" in '
            "trusted_owners.json in agent-config, or install and sign in to gh on this host.",
        )
    return Distrust(f"{owner}/{name} is a fork", FIX_OWNER) if fork else None


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


def is_fork(owner: str, name: str, trusted: TrustedOwners) -> bool | NoAnswer:
    """A declared repository is not a fork at once, with no lookup; otherwise ask the sources in order."""
    if trusted.declares(owner, name):
        return False
    cache = state_directory() / "forks" / f"{owner.lower()}__{name.lower()}"
    answer = cached_answer(cache)
    failures: list[str] = []
    for failure, ask in (
        ("gh is unavailable or gave no answer", github_answer),
        ("the public GitHub API gave no answer (private repository, rate limit or no network)", public_answer),
    ):
        if answer is not None:
            break
        answer = ask(owner, name)
        if answer is None:
            failures.append(failure)
    if answer is not None:
        remember(cache, answer)
        return answer == "true"
    return NoAnswer(tuple(failures) + (f"{owner}/{name} is not in the repositories list of trusted_owners.json",))


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


def public_answer(owner: str, name: str) -> str | None:
    """The fork flag of a public repository from GitHub, asked without credentials; private ones answer 404."""
    request = urllib.request.Request(
        PUBLIC_API.format(owner=owner, name=name),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "agent-harness-trusted-owners"},
    )
    try:
        with urllib.request.urlopen(request, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            fork = json.loads(response.read(PUBLIC_API_MAX_BYTES))["fork"]
    except OSError, ValueError, TypeError, KeyError, urllib.error.URLError:
        return None
    return {True: "true", False: "false"}.get(fork) if isinstance(fork, bool) else None


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
