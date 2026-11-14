"""The gh policy table: which operation each gh form performs, its effect, and which grant allows it.

The table keeps the shape a capability grant can reuse: a grant names a target class and the
operations or effects it allows there, and every operation no grant covers asks.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self

PATH_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+")
REST_PLACEHOLDERS = {"{owner}": r"(?P<owner>[A-Za-z0-9_.-]+)", "{repo}": r"(?P<repo>[A-Za-z0-9_.-]+)"}
REST_NUMBER = "[0-9]+"


class Effect(StrEnum):
    """What an operation changes, from nothing outside the machine to something that cannot be taken back."""

    READ = "read"
    LOCAL = "local"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class TargetClass(StrEnum):
    """Where a call acts, as far as the guard can tell before it runs."""

    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    UNRESOLVED = "unresolved"
    NODE = "node"


@dataclass(frozen=True, slots=True)
class Grant:
    """One row of target x operation x decision; `target` is a TargetClass value or "any"."""

    target: str
    effects: frozenset[Effect]
    operations: frozenset[str]
    justification: str

    def covers(self, target: TargetClass, operation: str, effect: Effect) -> bool:
        """Whether this grant allows the operation on the target."""
        return self.target in {"any", target.value} and (effect in self.effects or operation in self.operations)


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """A gh subcommand's operation and, for writes, every option it may take.

    `texts` carry prose sent to GitHub, `files` name local files whose content is sent, `repositories`
    name further target repositories, and `irreversible_flags` turn the operation irreversible.
    """

    operation: str
    effect: Effect
    values: frozenset[str] = frozenset()
    texts: frozenset[str] = frozenset()
    files: frozenset[str] = frozenset()
    repositories: frozenset[str] = frozenset()
    flags: frozenset[str] = frozenset()
    irreversible_flags: frozenset[str] = frozenset()

    @classmethod
    def from_json(cls, data: dict) -> Self:
        """Validate one command entry of the table."""
        lists = ("values", "texts", "files", "repositories", "flags", "irreversible_flags")
        if not set(data) <= {"operation", "effect", *lists} or not _is_name(data.get("operation")):
            raise ValueError("invalid command entry")
        return cls(data["operation"], Effect(data["effect"]), *(_options(data.get(key, [])) for key in lists))

    @property
    def value_options(self) -> frozenset[str]:
        """Options that take the next word, or the rest of their short bundle, as their value."""
        return self.values | self.texts | self.files | self.repositories


@dataclass(frozen=True, slots=True)
class RestRoute:
    """A REST write the table names, matched by method and path."""

    method: str
    pattern: re.Pattern[str]
    operation: str
    effect: Effect

    @classmethod
    def from_json(cls, data: dict) -> Self:
        """Validate one REST entry and compile its path template."""
        if set(data) != {"method", "path", "operation", "effect"} or not _is_name(data["operation"]):
            raise ValueError("invalid REST entry")
        segments = []
        for segment in str(data["path"]).split("/"):
            if segment in REST_PLACEHOLDERS:
                segments.append(REST_PLACEHOLDERS[segment])
            elif segment == "{number}":
                segments.append(REST_NUMBER)
            elif PATH_SEGMENT.fullmatch(segment):
                segments.append(re.escape(segment))
            else:
                raise ValueError(f"invalid REST path segment: {segment}")
        return cls(
            str(data["method"]).upper(), re.compile("/".join(segments)), data["operation"], Effect(data["effect"])
        )


@dataclass(frozen=True, slots=True)
class Operation:
    """An operation the table names and its effect."""

    name: str
    effect: Effect


@dataclass(frozen=True, slots=True)
class Catalog:
    """The whole gh policy table, validated once at load."""

    grants: tuple[Grant, ...]
    commands: dict[str, CommandSpec]
    rest: tuple[RestRoute, ...]
    mutations: dict[str, Operation]

    def grant(self, target: TargetClass, operation: str, effect: Effect) -> Grant | None:
        """The first grant that allows the operation on the target, or None when it must ask."""
        return next((grant for grant in self.grants if grant.covers(target, operation, effect)), None)

    def route(self, method: str, path: str) -> RestRoute | None:
        """The REST write the method and path perform, or None when the table does not name it."""
        return next((route for route in self.rest if route.method == method and route.pattern.fullmatch(path)), None)


def load(path: Path) -> Catalog:
    """Read and validate the table, so a malformed file never widens what runs unprompted."""
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("invalid version")
        return Catalog(
            tuple(_grant(item) for item in data["grants"]),
            {_command_key(key): CommandSpec.from_json(value) for key, value in data["commands"].items()},
            tuple(RestRoute.from_json(item) for item in data["rest"]),
            {_mutation_name(name): _operation(value) for name, value in data["graphql_mutations"].items()},
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"invalid gh policy: {path}") from error


def _mutation_name(name: str) -> str:
    if not re.fullmatch(r"[a-z][A-Za-z]*", name):
        raise ValueError(f"invalid GraphQL mutation name: {name}")
    return name


def _operation(data: dict) -> Operation:
    if set(data) != {"operation", "effect"} or not _is_name(data["operation"]):
        raise ValueError("invalid GraphQL mutation entry")
    return Operation(data["operation"], Effect(data["effect"]))


def _grant(data: dict) -> Grant:
    if data.get("decision") != "allow" or not isinstance(data.get("justification"), str) or not data["justification"]:
        raise ValueError("a grant allows and says why")
    target = data["target"]
    if target != "any":
        TargetClass(target)
    effects = frozenset(Effect(effect) for effect in data.get("effects", []))
    operations = frozenset(data.get("operations", []))
    if (not effects and not operations) or not all(_is_name(item) for item in operations):
        raise ValueError("a grant names effects or operations")
    return Grant(target, effects, operations, data["justification"])


def _command_key(key: str) -> str:
    if not re.fullmatch(r"[a-z-]+ [a-z-]+", key):
        raise ValueError(f"invalid command key: {key}")
    return key


def _options(values: object) -> frozenset[str]:
    if not isinstance(values, list) or not all(
        isinstance(value, str) and re.fullmatch(r"-[A-Za-z]|--[a-z][a-z-]*", value) for value in values
    ):
        raise ValueError("invalid option list")
    return frozenset(values)


def _is_name(value: object) -> bool:
    """Whether the value names an operation as kind.operation."""
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z_]+\.[a-z_]+", value))
