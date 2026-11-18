from dataclasses import dataclass, field

import pydantic


@dataclass
class Money:
    amount: int
    currency: str


@dataclass(slots=True)
class EmailAddress:
    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise ValueError(f"cannot create an email address from {self.value!r}: no @")


class DateRange(pydantic.BaseModel):
    start: str
    end: str


@dataclass(slots=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: float


@dataclass(frozen=True, slots=True)
class Sku:
    value: str


@dataclass(slots=True)
class Cart:
    items: list[str] = field(default_factory=list)

    def add(self, sku):
        self.items.append(sku)


class Account(pydantic.BaseModel):
    account_id: str
    balance: int

    def deposit(self, amount):
        self.balance += amount


class Coordinates(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    latitude: float
    longitude: float


@dataclass
class QueryBuilder:
    table: str
    filters: list[str] = field(default_factory=list)

    def where(self, condition):
        self.filters.append(condition)
        return self
