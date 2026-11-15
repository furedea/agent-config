# Models and Construction

## Classes

- Use `__slots__` to restrict variables when not using `dataclasses` or `pydantic`

```python
class Foo:
    __slots__ = ("name", "age")

    def __init__(self, name: str, age: int) -> None:
        self.name = name
        self.age = age
```

- Value Objects:
    - Use `@dataclass(frozen=True, slots=True)` for internal value objects; `slots=True` generates `__slots__`, so do not write it by hand
    - Use pydantic only at boundaries that parse untrusted input (API, JSON, config files), and do not pass boundary models into the domain (see [Pydantic](#pydantic))
    - Resolve routine representation choices from existing dependencies and nearby code. Ask only
      when a material dependency or compatibility decision is not covered by the user's request.
    - Check domain invariants in `__post_init__`, not types:

```python
@dataclass(frozen=True, slots=True)
class Age:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError(f"Age must be non-negative, got {self.value}")
```

- **Use classmethods as alternative constructors for pure construction** (no I/O). `from_X`, `parse_X`, `create_X`, `make_X` → classmethod. **If construction involves I/O (network, file system), separate into a module-level function** to keep the Value Object pure and testable.

```python
from typing import Self


@dataclass(frozen=True, slots=True)
class SWEInstance:
    instance_id: str
    repo: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Self:  # pure → classmethod
        return cls(instance_id=data["id"], repo=data["repo"])


def load_instance(instance_id: str) -> SWEInstance:  # I/O → module-level function
    row = fetch_from_dataset(instance_id)
    return SWEInstance.from_dict(row)


# WRONG — module-level factory for pure construction:
def swe_instance_from_dict(data: dict) -> SWEInstance: ...  # move inside as classmethod
```

## Pydantic

Boundary schemas inherit one shared base class; only the class named `FrozenBaseModel` may inherit `pydantic.BaseModel` directly. Place it next to the boundary models (for example `schemas/base.py`; the location is not fixed). Parse JSON with `Model.model_validate_json(...)`.

```python
"""Base model for schemas that parse untrusted input at a boundary."""

import pydantic


class FrozenBaseModel(pydantic.BaseModel):
    """Freeze a parsed schema and validate it strictly."""

    model_config = pydantic.ConfigDict(
        frozen=True, extra="forbid", strict=True, validate_default=True, revalidate_instances="always"
    )
```

## Enums

- Use `Enum`/`StrEnum` for fixed choices instead of raw string literals or dict maps
- Convert user input strings to Enum early, then map through Enum values
- Prefer `StrEnum` when values are serialized or user-facing
