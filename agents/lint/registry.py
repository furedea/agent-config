"""Lint rule registry: the declared shape of one rule and the checks that keep it traceable to its source text.

Only the standard library is used so that hooks can import this module. Reading the YAML rule files is a
development-time job (see tests/lint_registry.py); this module validates the already-parsed mappings.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Self


class Method(StrEnum):
    """How a rule is judged."""

    LINTER = "linter"
    AST_GREP = "ast-grep"
    MODEL = "model"
    PROSE = "prose"


class RuleError(ValueError):
    """A rule mapping or registry that breaks the schema."""


@dataclass(frozen=True, slots=True)
class Source:
    """The line of a prose file that states the rule, with the rule text quoted from it."""

    file: str
    line: int
    text: str

    def __post_init__(self) -> None:
        if not self.file or PurePosixPath(self.file).is_absolute() or ".." in PurePosixPath(self.file).parts:
            raise RuleError(f"source.file must be a repository-relative path, got {self.file!r}")
        if self.line < 1:
            raise RuleError(f"source.line must be at least 1, got {self.line}")
        if not self.text.strip():
            raise RuleError("source.text must quote the rule text")

    @classmethod
    def from_mapping(cls, data: object) -> Self:
        fields = _Fields(data, "source", frozenset({"file", "line", "text"}))
        return cls(
            file=fields.required("file", str), line=fields.required("line", int), text=fields.required("text", str)
        )


@dataclass(frozen=True, slots=True)
class Examples:
    """Snippets a rule must accept (conforming) and must flag (violating)."""

    conforming: tuple[str, ...]
    violating: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, snippets in (("conforming", self.conforming), ("violating", self.violating)):
            if not snippets:
                raise RuleError(f"examples.{name} needs at least one example")
            if not all(snippet.strip() for snippet in snippets):
                raise RuleError(f"examples.{name} must not contain a blank example")

    @classmethod
    def from_mapping(cls, data: object) -> Self:
        fields = _Fields(data, "examples", frozenset({"conforming", "violating"}))
        return cls(conforming=fields.strings("conforming"), violating=fields.strings("violating"))


@dataclass(frozen=True, slots=True)
class Rule:
    """One declared rule.

    `code` is the linter's own rule code and belongs to `linter` rules only; `threshold` is the model score at
    which a unit counts as violating and belongs to `model` rules only.
    """

    id: str
    source: Source
    language: str
    method: Method
    version: int
    examples: Examples
    code: str | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.language.strip():
            raise RuleError("id and language must not be blank")
        if self.version < 1:
            raise RuleError(f"{self.id}: version must be at least 1, got {self.version}")
        self._require_only_for(self.code, "code", Method.LINTER)
        self._require_only_for(self.threshold, "threshold", Method.MODEL)
        if self.threshold is not None and not 0 < self.threshold <= 1:
            raise RuleError(f"{self.id}: threshold must be in (0, 1], got {self.threshold}")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> Self:
        fields = _Fields(data, "rule", _RULE_FIELDS)
        return cls(
            id=fields.required("id", str),
            source=Source.from_mapping(fields.raw("source")),
            language=fields.required("language", str),
            method=_method(fields.required("method", str)),
            version=fields.required("version", int),
            examples=Examples.from_mapping(fields.raw("examples")),
            code=fields.optional("code", str),
            threshold=fields.number("threshold"),
        )

    def _require_only_for(self, value: object, name: str, method: Method) -> None:
        if self.method is method and value is None:
            raise RuleError(f"{self.id}: a {method} rule requires {name}")
        if self.method is not method and value is not None:
            raise RuleError(f"{self.id}: {name} is only allowed on {method} rules")


@dataclass(frozen=True, slots=True)
class Registry:
    """All declared rules, with unique ids."""

    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        ids = [rule.id for rule in self.rules]
        duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
        if duplicates:
            raise RuleError(f"duplicate rule ids: {', '.join(duplicates)}")

    @classmethod
    def from_rules(cls, rules: Sequence[Rule]) -> Self:
        return cls(rules=tuple(rules))

    def __iter__(self) -> Iterator[Rule]:
        return iter(self.rules)


def source_problem(source: Source, root: Path) -> str | None:
    """Return why the source link no longer holds, or None when the cited line still quotes the rule."""
    path = root / source.file
    if not path.is_file():
        return f"{source.file} does not exist"
    lines = path.read_text(encoding="utf-8").splitlines()
    if source.line > len(lines):
        return f"{source.file} has {len(lines)} lines, so line {source.line} does not exist"
    if _squash(source.text) not in _squash(lines[source.line - 1]):
        return f"{source.file}:{source.line} no longer contains {source.text!r}"
    return None


_RULE_FIELDS = frozenset({"id", "source", "language", "method", "version", "examples", "code", "threshold"})


def _squash(text: str) -> str:
    return " ".join(text.split())


class _Fields:
    """Typed access to the fields of one parsed mapping, naming the mapping in every error."""

    def __init__(self, data: object, where: str, allowed: frozenset[str]) -> None:
        if not isinstance(data, Mapping):
            raise RuleError(f"{where} must be a mapping")
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise RuleError(f"{where} has unknown fields: {', '.join(unknown)}")
        self._data: Mapping[str, object] = data
        self._where = where

    def required[T](self, key: str, kind: type[T]) -> T:
        if key not in self._data:
            raise RuleError(f"{self._where}.{key} is required")
        return self._typed(key, kind)

    def optional[T](self, key: str, kind: type[T]) -> T | None:
        return self._typed(key, kind) if key in self._data else None

    def raw(self, key: str) -> object:
        return self._data.get(key)

    def strings(self, key: str) -> tuple[str, ...]:
        value = self._data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise RuleError(f"{self._where}.{key} must be a list of strings")
        return tuple(value)

    def number(self, key: str) -> float | None:
        value = self._data.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RuleError(f"{self._where}.{key} must be a number, got {value!r}")
        return float(value)

    def _typed[T](self, key: str, kind: type[T]) -> T:
        value = self._data[key]
        if isinstance(value, bool) or not isinstance(value, kind):
            raise RuleError(f"{self._where}.{key} must be {kind}, got {value!r}")
        return value


def _method(value: str) -> Method:
    try:
        return Method(value)
    except ValueError:
        allowed = ", ".join(method.value for method in Method)
        raise RuleError(f"method must be one of {allowed}, got {value!r}") from None
