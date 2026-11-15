"""Check the file names and metadata of the ADRs under `docs/adr/` and describe each violation."""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

STATUSES = ("Proposed", "Accepted", "Superseded", "Deprecated")
# `Superseded by` and the provenance keys already used by the repository's ADRs are vocabulary too.
RELATION_KEYS = ("Supersedes", "Superseded by", "Partly superseded by", "Refines", "Related")
PLAIN_KEYS = ("Status", "Date", "Amended", "Originally", "Historical sources")
KEYS = frozenset(RELATION_KEYS + PLAIN_KEYS)
FILE_NAME = re.compile(r"(\d{4})_[a-z0-9]+(?:_[a-z0-9]+)*\.md")
TITLE = re.compile(r"# ADR-(\d{4}): \S.*")
METADATA = re.compile(r"- ([A-Za-z][A-Za-z ]*): ?(.*)")
AMENDED = re.compile(r"\d{4}-\d{2}-\d{2} \(.+\)")
# A reference qualified by a repository word, such as `dotfiles ADR-0016`, names another repository's ADR.
LOCAL_REFERENCE = re.compile(r"(?<![\w/.-] )(?<![\w/.-])ADR-(\d{4})(?!\d)")
EXEMPT_NAMES = frozenset({"README.md"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation, located by file and line."""

    path: Path
    line: int
    message: str

    def describe(self) -> str:
        """Format the finding like the other hook diagnostics."""
        return f"ADR metadata · {self.path}:{self.line}\n{self.message}"


@dataclass(slots=True)
class Adr:
    """One ADR file: the ID from its name, its metadata entries, and the problems found while reading it."""

    path: Path
    identifier: str | None
    metadata: list[tuple[int, str, str]] = field(default_factory=list)
    title_line: int = 1
    problems: list[Finding] = field(default_factory=list)

    def values(self, key: str) -> list[str]:
        """Return the values of every metadata entry named `key`."""
        return [value.strip() for _, name, value in self.metadata if name == key]

    def references(self, key: str) -> list[tuple[int, str]]:
        """Return the line and ID of every local ADR reference in the entries named `key`."""
        return [
            (line, match.group(1))
            for line, name, value in self.metadata
            if name == key
            for match in LOCAL_REFERENCE.finditer(value)
        ]

    def report(self, line: int, message: str) -> None:
        """Record a problem found while reading this file."""
        self.problems.append(Finding(self.path, line, message))


def diagnostics(paths: Iterable[Path]) -> tuple[str, ...]:
    """Describe violations in every ADR directory that holds one of the edited files; stay silent otherwise."""
    directories = dict.fromkeys(path.parent for path in paths if is_adr_file(path))
    findings = (finding for directory in directories for finding in check_directory(directory))
    return tuple(finding.describe() for finding in sorted(findings, key=lambda f: (f.path, f.line, f.message)))


def is_adr_file(path: Path) -> bool:
    """Tell whether a path is a Markdown file directly under a `docs/adr/` directory."""
    return path.suffix == ".md" and path.parent.name == "adr" and path.parent.parent.name == "docs"


def check_directory(directory: Path) -> list[Finding]:
    """Check each ADR of a directory, then the rules that span ADRs."""
    adrs = [read_adr(path) for path in sorted(directory.glob("*.md")) if path.name not in EXEMPT_NAMES]
    findings = [problem for adr in adrs for problem in adr.problems]
    findings += duplicate_identifiers(adrs)
    findings += unknown_references(adrs)
    findings += unsuperseded_targets(adrs)
    findings += skipped_identifiers(adrs)
    return findings


def read_adr(path: Path) -> Adr:
    """Read one ADR file and record the problems visible in it alone."""
    name_match = FILE_NAME.fullmatch(path.name)
    adr = Adr(path, name_match.group(1) if name_match else None)
    if name_match is None:
        adr.report(1, "File name must be `NNNN_<words>.md`: four digits, lowercase words joined by `_`.")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    check_title(adr, lines)
    adr.metadata = metadata_entries(lines[adr.title_line :], adr.title_line)
    check_metadata(adr)
    return adr


def check_title(adr: Adr, lines: list[str]) -> None:
    """Require the first non-blank line to be `# ADR-NNNN: <title>` with the file name's ID."""
    index = next((i for i, line in enumerate(lines) if line.strip()), None)
    if index is None:
        adr.report(1, "Title line `# ADR-NNNN: <title>` is missing.")
        return
    adr.title_line = index + 1
    title = TITLE.fullmatch(lines[index].rstrip())
    if title is None:
        adr.report(adr.title_line, "Title line must be `# ADR-NNNN: <title>`.")
    elif adr.identifier is not None and title.group(1) != adr.identifier:
        adr.report(adr.title_line, f"Title ID ADR-{title.group(1)} does not match the file name ID {adr.identifier}.")


def metadata_entries(lines: list[str], offset: int) -> list[tuple[int, str, str]]:
    """Read the `- Key: value` block after the title; an indented line continues the previous entry."""
    entries: list[tuple[int, str, str]] = []
    for number, line in enumerate(lines, start=offset + 1):
        match = METADATA.fullmatch(line.rstrip())
        if match:
            entries.append((number, match.group(1), match.group(2)))
        elif entries and line[:1].isspace() and line.strip():
            last = entries[-1]
            entries[-1] = (last[0], last[1], f"{last[2]} {line.strip()}")
        elif entries or line.strip():
            break
    return entries


def check_metadata(adr: Adr) -> None:
    """Require a valid status and keep every entry within the vocabulary."""
    for number, key, value in adr.metadata:
        problem = entry_problem(key, value.strip())
        if problem:
            adr.report(number, problem)
    if not adr.values("Status"):
        adr.report(adr.title_line, "Metadata `- Status:` is missing.")


def entry_problem(key: str, value: str) -> str:
    """Describe what is wrong with one metadata entry, or return an empty string."""
    if key not in KEYS:
        return f"Unknown metadata key `{key}`; allowed: {', '.join(sorted(KEYS))}."
    if key == "Status" and value not in STATUSES:
        return f"Status must be one of {', '.join(STATUSES)}; found `{value}`."
    if key == "Amended" and not AMENDED.fullmatch(value):
        return "Amended must be `<YYYY-MM-DD> (<what>)`."
    return ""


def duplicate_identifiers(adrs: list[Adr]) -> list[Finding]:
    """Report every ADR that shares its ID with another."""
    by_identifier: dict[str, list[Adr]] = defaultdict(list)
    for adr in adrs:
        if adr.identifier is not None:
            by_identifier[adr.identifier].append(adr)
    return [
        Finding(adr.path, 1, f"ID {identifier} is used by more than one ADR: {', '.join(a.path.name for a in same)}.")
        for identifier, same in by_identifier.items()
        if len(same) > 1
        for adr in same
    ]


def unknown_references(adrs: list[Adr]) -> list[Finding]:
    """Report relation entries that name an ADR missing from the directory."""
    known = {adr.identifier for adr in adrs}
    return [
        Finding(adr.path, line, f"{key} names ADR-{identifier}, which does not exist in this directory.")
        for adr in adrs
        for key in RELATION_KEYS
        for line, identifier in adr.references(key)
        if identifier not in known
    ]


def unsuperseded_targets(adrs: list[Adr]) -> list[Finding]:
    """Report an ADR named by `Supersedes` whose own Status is not `Superseded`."""
    statuses = {adr.identifier: adr.values("Status") for adr in adrs}
    return [
        Finding(adr.path, line, f"ADR-{identifier} is superseded here, so its Status must be `Superseded`.")
        for adr in adrs
        for line, identifier in adr.references("Supersedes")
        if identifier in statuses and "Superseded" not in statuses[identifier]
    ]


def skipped_identifiers(adrs: list[Adr]) -> list[Finding]:
    """Report the newest ADR when its ID skips numbers, but only while the earlier history has no gap."""
    numbers = sorted({int(adr.identifier) for adr in adrs if adr.identifier is not None})
    if len(numbers) < 3 or numbers[-1] - numbers[-2] == 1:
        return []
    earlier = numbers[:-1]
    if earlier != list(range(earlier[0], earlier[-1] + 1)):
        return []
    skipped = numbers[-1] - numbers[-2] - 1
    message = f"ID {numbers[-1]:04d} skips {skipped} number(s) after ADR-{numbers[-2]:04d}."
    return [Finding(adr.path, 1, message) for adr in adrs if adr.identifier == f"{numbers[-1]:04d}"]
