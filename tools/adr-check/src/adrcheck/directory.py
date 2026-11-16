"""Check every ADR file of one directory and report all findings."""

from pathlib import Path

from adrcheck import history, references
from adrcheck.document import Document, InvalidDocumentError, adr_number, parse, shape_errors
from adrcheck.references import Finding


def check(directory: Path, base: str | None = None) -> tuple[Finding, ...]:
    """Findings for the ADRs in `directory`; with `base`, also for accepted ADRs that changed since that commit."""
    files = sorted(path for path in directory.glob("*.md") if path.is_file())
    documents: dict[str, Document] = {}
    shapes: dict[str, dict] = {}
    findings: list[Finding] = []
    for path in files:
        try:
            document = parse(path.name, path.read_text())
        except InvalidDocumentError as error:
            findings.append(Finding(path.name, str(error)))
            continue
        documents[path.name] = document
        errors = shape_errors(document.front_matter)
        findings += [Finding(path.name, message) for message in errors]
        if not errors and isinstance(document.front_matter, dict):
            shapes[path.name] = document.front_matter
    findings += _duplicate_numbers(files)
    findings += references.check(_existing_ids(files), shapes)
    if base is not None:
        findings += history.check(directory, base, _documents_by_number(files, documents))
    return tuple(findings)


def _duplicate_numbers(files: list[Path]) -> list[Finding]:
    by_number: dict[str, list[str]] = {}
    for path in files:
        number = adr_number(path.name)
        if number is not None:
            by_number.setdefault(number, []).append(path.name)
    return [
        Finding(name, f"ID ADR-{number} is also used by {', '.join(n for n in names if n != name)}")
        for number, names in by_number.items()
        if len(names) > 1
        for name in names
    ]


def _documents_by_number(files: list[Path], documents: dict[str, Document]) -> dict[str, Document | None]:
    return {number: documents.get(path.name) for path in files if (number := adr_number(path.name))}


def _existing_ids(files: list[Path]) -> frozenset[str]:
    return frozenset(f"ADR-{number}" for path in files if (number := adr_number(path.name)))
