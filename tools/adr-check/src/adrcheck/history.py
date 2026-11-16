"""Protect accepted ADRs: against a base commit they may not be removed, renumbered, or have their body changed."""

import subprocess
from collections.abc import Mapping
from pathlib import Path

from adrcheck.document import Document, InvalidDocumentError, adr_number, parse
from adrcheck.references import Finding

ACCEPTED = "accepted"


class BaseUnreadableError(Exception):
    """git could not give the ADRs at the base commit."""


def check(directory: Path, base: str, current: Mapping[str, Document | None]) -> tuple[Finding, ...]:
    """Findings for each ADR accepted at `base` that `current` removed or rewrote.

    `current` maps each ID number present now to its document, or to None when the file cannot be read as one; the
    file is still there, and the parse failure is reported elsewhere.
    """
    findings = []
    for file_name, text in _files_at(directory, base).items():
        accepted = _accepted_at_base(file_name, text)
        if accepted is None:
            continue
        if accepted.number not in current:
            findings.append(Finding(file_name, f"accepted at {base} but removed or renumbered"))
        elif (now := current[accepted.number]) is not None and now.body != accepted.body:
            findings.append(Finding(file_name, f"accepted at {base} but its body changed; record changes in amended"))
    return tuple(findings)


def _accepted_at_base(file_name: str, text: str) -> Document | None:
    try:
        document = parse(file_name, text)
    except InvalidDocumentError:
        return None
    front_matter = document.front_matter
    if isinstance(front_matter, dict) and front_matter.get("status") == ACCEPTED:
        return document
    return None


def _files_at(directory: Path, base: str) -> dict[str, str]:
    listing = _git(directory, "ls-tree", "--name-only", "-z", base, "./")
    names = [name for name in listing.split("\0") if adr_number(name) is not None]
    return {name: _git(directory, "show", f"{base}:./{name}") for name in names}


def _git(directory: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BaseUnreadableError(result.stderr.strip() or f"git {arguments[0]} failed")
    return result.stdout
