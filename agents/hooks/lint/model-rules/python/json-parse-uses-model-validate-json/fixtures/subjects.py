import json
import tomllib
import uuid
from decimal import Decimal
from pathlib import Path

import orjson

from shop.schemas import Invoice, Order, Response, Settings


def parse_order(raw: str) -> Order:
    return Order.model_validate(json.loads(raw))


def load_settings(path: Path) -> Settings:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Settings.model_validate(data)


def parse_invoice(body: bytes) -> Invoice:
    payload = orjson.loads(body)
    invoice = Invoice.model_validate(payload)
    return invoice


def parse_priced_order(raw: str) -> Order:
    return Order.model_validate(json.loads(raw, parse_float=Decimal))


def load_toml_settings(path: Path) -> Settings:
    return Settings.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def default_order(customer_id: str) -> Order:
    return Order.model_validate({"customer_id": customer_id, "lines": []})


def parse_new_order(raw: str) -> Order:
    data = json.loads(raw)
    data["order_id"] = str(uuid.uuid4())
    return Order.model_validate(data)


def respond(payload: dict) -> Response:
    return Response(Order.model_validate(payload))
