"""Check the references between the ADRs of one directory: existence, and supersession in both directions."""

from collections.abc import Mapping
from dataclasses import dataclass

REFERENCE_KEYS = ("supersedes", "superseded-by", "partly-superseded-by", "related")
SUPERSESSION_KEYS = ("superseded-by", "partly-superseded-by")
ID_PREFIX = "ADR-"

Shape = Mapping[str, list[str]]


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation, tied to the ADR file it is reported against."""

    file_name: str
    message: str

    def __str__(self) -> str:
        return f"{self.file_name}: {self.message}"


def check(existing: frozenset[str], shapes: Mapping[str, Shape]) -> tuple[Finding, ...]:
    """Findings for `shapes`, the schema-valid front matter by file name.

    `existing` holds every ADR ID in the directory.

    Only IDs without a repository prefix are resolved; an ID of another repository is left alone.
    """
    owners = {_number(file_name): file_name for file_name in shapes}
    findings = [*_missing_targets(existing, shapes)]
    findings += _supersedes_without_reverse(owners, shapes)
    findings += _superseded_without_forward(owners, shapes)
    return tuple(findings)


def _missing_targets(existing: frozenset[str], shapes: Mapping[str, Shape]) -> list[Finding]:
    return [
        Finding(file_name, f"{key} names {reference}, which does not exist in this directory")
        for key in REFERENCE_KEYS
        for file_name, reference in _links(shapes, (key,))
        if reference not in existing
    ]


def _supersedes_without_reverse(owners: Mapping[str, str], shapes: Mapping[str, Shape]) -> list[Finding]:
    return [
        Finding(
            file_name,
            f"supersedes {reference}, but {target} names {_id(file_name)} in neither "
            "superseded-by nor partly-superseded-by",
        )
        for file_name, reference in _links(shapes, ("supersedes",))
        if (target := owners.get(_strip(reference))) is not None
        and _id(file_name) not in _supersession_ids(shapes[target])
    ]


def _superseded_without_forward(owners: Mapping[str, str], shapes: Mapping[str, Shape]) -> list[Finding]:
    return [
        Finding(
            file_name,
            f"names {reference} as its successor, but {successor} does not list {_id(file_name)} in supersedes",
        )
        for file_name, reference in _links(shapes, SUPERSESSION_KEYS)
        if (successor := owners.get(_strip(reference))) is not None
        and _id(file_name) not in shapes[successor].get("supersedes", [])
    ]


def _links(shapes: Mapping[str, Shape], keys: tuple[str, ...]) -> list[tuple[str, str]]:
    """Every (file name, unprefixed reference) that the files hold under `keys`."""
    return [
        (file_name, reference)
        for file_name, shape in shapes.items()
        for key in keys
        for reference in _local(shape, key)
    ]


def _supersession_ids(shape: Shape) -> list[str]:
    return [reference for key in SUPERSESSION_KEYS for reference in _local(shape, key)]


def _local(shape: Shape, key: str) -> list[str]:
    return [reference for reference in shape.get(key, []) if "/" not in reference]


def _number(file_name: str) -> str:
    return file_name[:4]


def _id(file_name: str) -> str:
    return f"{ID_PREFIX}{_number(file_name)}"


def _strip(reference: str) -> str:
    return reference.removeprefix(ID_PREFIX)
