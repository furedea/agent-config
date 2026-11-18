import os

import requests

from shop.text import slugify


def database_url():
    return os.environ.get("SHOP_DATABASE_URL", "sqlite:///shop.db")


def request_id(headers):
    return headers["X-Request-Id"]


def archive_if_done(order):
    if order.status == "archived":
        return
    if order.status == "delivered":
        order.status = "archived"


def fetch_users():
    return requests.get("https://api.example.com/v1/users", timeout=5).json()


def test_slugify_joins_words():
    assert slugify("Hello World") == "hello-world"


def test_unknown_order_returns_404(client):
    response = client.get("/orders/42")
    assert response.json()["detail"] == "Order 42 not found"


def soft_limit():
    limits = {"soft": 10, "hard": 20}
    return limits["soft"]
