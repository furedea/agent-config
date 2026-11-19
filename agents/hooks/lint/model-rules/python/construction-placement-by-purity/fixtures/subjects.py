import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import httpx


@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str

    @classmethod
    def from_text(cls, text: str) -> Self:
        amount, currency = text.split()
        return cls(int(amount), currency)

    @classmethod
    def from_rates_service(cls, url: str) -> Self:
        response = httpx.get(url, timeout=5.0)
        body = response.json()
        return cls(int(body["amount"]), body["currency"])


@dataclass(frozen=True, slots=True)
class Port:
    number: int

    @classmethod
    def from_environment(cls) -> Self:
        return cls(int(os.environ["APP_PORT"]))

    @staticmethod
    def parse_text(text: str) -> Port:
        return Port(int(text.strip()))


@dataclass(frozen=True, slots=True)
class Config:
    name: str
    retries: int

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> Self:
        return cls(name=str(data["name"]), retries=int(data.get("retries", 3)))


def money_from_cents(cents: int, currency: str) -> Money:
    return Money(cents // 100, currency)


def parse_port(text: str) -> Port:
    return Port(int(text.strip()))


def make_config_from_file(path: Path) -> Config:
    return Config.from_mapping(json.loads(path.read_text()))


def create_http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(timeout=timeout_seconds)


def parse_header(line: str) -> tuple[str, str]:
    name, _, value = line.partition(":")
    return name.strip().lower(), value.strip()
