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
METADATA = re.compile(r"- ([A-Za-z][\w -]*): ?(.*)")
AMENDED = re.compile(r"\d{4}-\d{2}-\d{2} \(.+\)")
# A reference qualified by a repository word, such as `dotfiles ADR-0016`, names another repository's ADR.
REFERENCE = re.compile(r"(?:\[?([A-Za-z][\w/.-]*) )?ADR-(\d{4})(?!\d)")
JOINERS = frozenset({"and", "or", "to", "by", "with", "of", "in", "from", "see"})
EXEMPT_NAMES = frozenset({"README.md"})
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation, located by file and line."""

    path: Path
    line: int
    message: str
    also_involves: tuple[Path, ...] = ()

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
            (line, match.group(2))
            for line, name, value in self.metadata
            if name == key
            for match in REFERENCE.finditer(value)
            if match.group(1) is None or match.group(1) in JOINERS
        ]

    def report(self, line: int, message: str) -> None:
        """Record a problem found while reading this file."""
        self.problems.append(Finding(self.path, line, message))


def diagnostics(paths: Iterable[Path]) -> tuple[str, ...]:
    """Describe the violations that involve an edited ADR; stay silent for other files and for clean ADRs.

    The whole directory is read, because uniqueness, references and supersession span files, but a violation in an
    ADR the edit did not touch is not reported, so a repository with another ADR convention is not flooded. A
    deleted ADR leaves no file to match, so a deletion reports every violation of its directory.
    """
    edited = {path.resolve() for path in paths if is_adr_file(path)}
    directories = dict.fromkeys(path.parent for path in edited)
    deleted = {path.parent for path in edited if not path.exists()}
    findings = (
        finding
        for directory in directories
        if follows_convention(directory, edited)
        for finding in check_directory(directory)
        if directory in deleted or edited & {finding.path.resolve(), *(p.resolve() for p in finding.also_involves)}
    )
    return tuple(finding.describe() for finding in sorted(findings, key=lambda f: (f.path, f.line, f.message)))


def is_adr_file(path: Path) -> bool:
    """Tell whether a path is a Markdown file directly under a `docs/adr/` directory."""
    return (
        path.name not in EXEMPT_NAMES
        and path.suffix.lower() in MARKDOWN_SUFFIXES
        and path.parent.name == "adr"
        and path.parent.parent.name == "docs"
    )


def follows_convention(directory: Path, edited: set[Path]) -> bool:
    """Tell whether the ADRs beside the edited ones are named like this check expects.

    A directory whose other ADRs all use another scheme, such as adr-tools' `0001-title.md`, keeps its own
    convention, so none of its ADRs is reported.
    """
    others = [path for path in markdown_files(directory) if path.resolve() not in edited]
    return not others or any(FILE_NAME.fullmatch(path.name) for path in others)


def markdown_files(directory: Path) -> list[Path]:
    """List the Markdown files of an ADR directory except the exempt ones."""
    return sorted(
        path
        for path in directory.iterdir()
        if path.suffix.lower() in MARKDOWN_SUFFIXES and path.is_file() and path.name not in EXEMPT_NAMES
    )


def check_directory(directory: Path) -> list[Finding]:
    """Check each ADR of a directory, then the rules that span ADRs."""
    adrs = [read_adr(path) for path in markdown_files(directory)]
    findings = [problem for adr in adrs for problem in adr.problems]
    findings += duplicate_identifiers(adrs)
    findings += unknown_references(adrs)
    findings += unsuperseded_targets(adrs)
    findings += unsuperseded_adrs(adrs)
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
    count = len(adr.values("Status"))
    if count != 1:
        adr.report(adr.title_line, f"Exactly one `- Status:` is required; found {count}.")


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
        Finding(
            adr.path,
            1,
            f"ID {identifier} is used by more than one ADR: {', '.join(a.path.name for a in same)}.",
            tuple(a.path for a in same),
        )
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


def unsuperseded_adrs(adrs: list[Adr]) -> list[Finding]:
    """Report an ADR that names its replacement in `Superseded by` but whose own Status is not `Superseded`."""
    return [
        Finding(adr.path, line, f"Superseded by ADR-{identifier} requires `- Status: Superseded`.")
        for adr in adrs
        for line, identifier in adr.references("Superseded by")
        if "Superseded" not in adr.values("Status")
    ]


def unsuperseded_targets(adrs: list[Adr]) -> list[Finding]:
    """Report an ADR named by `Supersedes` whose own Status is not `Superseded`."""
    by_identifier = {adr.identifier: adr for adr in adrs}
    return [
        Finding(
            adr.path,
            line,
            f"ADR-{identifier} is superseded here, so its Status must be `Superseded`.",
            (by_identifier[identifier].path,),
        )
        for adr in adrs
        for line, identifier in adr.references("Supersedes")
        if identifier in by_identifier and "Superseded" not in by_identifier[identifier].values("Status")
    ]
