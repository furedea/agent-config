"""Read the 1Password service-account credentials the model rules need from the macOS Keychain.

The token is the only secret the hook ever holds. It is never printed or logged and is kept out of `repr`, so an
error message or a test failure cannot show it. The key that `jev-lint` uses is never read here: `op` injects it into
the `jev-lint` process.
"""

import getpass
import os
import re
import subprocess
from dataclasses import dataclass, field

from model_rules_outcome import Prevented

TOKEN_SERVICE = "agent-model-rules-op-token"
ENVIRONMENT_SERVICE = "agent-model-rules-op-environment"
LOOKUP_TIMEOUT_SECONDS = 5
# The Environment ID is not a UUID (for example 26 lowercase base32 characters), so it is checked loosely.
ENVIRONMENT_ID = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class Credentials:
    """A service-account token and the 1Password Environment it may read."""

    token: str = field(repr=False)
    environment: str


def load() -> Credentials | Prevented:
    """Read both Keychain items for the current user; a missing or malformed item names its service, never a value."""
    account = os.environ.get("USER") or getpass.getuser()
    token = _item(account, TOKEN_SERVICE)
    environment = _item(account, ENVIRONMENT_SERVICE)
    if isinstance(token, Prevented):
        return token
    if isinstance(environment, Prevented):
        return environment
    if not ENVIRONMENT_ID.fullmatch(environment):
        return Prevented(f"Keychain item {ENVIRONMENT_SERVICE} is not a 1Password Environment ID")
    return Credentials(token, environment)


def _item(account: str, service: str) -> str | Prevented:
    arguments = ["security", "find-generic-password", "-a", account, "-s", service, "-w"]
    try:
        result = subprocess.run(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return Prevented("the Keychain cannot be read on this host")
    value = result.stdout.decode(errors="replace").strip()
    if result.returncode != 0 or not value or any(character.isspace() for character in value):
        return Prevented(f"Keychain item {service} is missing or unusable")
    return value
