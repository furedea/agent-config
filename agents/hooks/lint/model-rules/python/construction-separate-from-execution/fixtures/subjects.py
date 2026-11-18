import argparse
import os

from shop.clients import FakeShopClient, ShopClient
from shop.mail import MailServer
from shop.orders import OrderService, sync_orders
from shop.storage import Connection, CsvReader, InMemoryOrderStore, OrderRepository, ProductStore


def sync_recent_orders(since):
    client = ShopClient(api_key=os.environ["SHOP_KEY"], timeout=10)
    repository = OrderRepository(Connection(os.environ["DATABASE_URL"], pool_size=4))
    for order in client.list_orders(since=since):
        if order.total > 0:
            repository.save(order)


def send_digest(users, digest):
    server = MailServer(host="smtp.example.com", port=587)
    server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
    for user in users:
        if user.wants_digest:
            server.send(user.email, digest.render_for(user))


def import_products(path):
    reader = CsvReader(path, delimiter=";")
    store = ProductStore(Connection(os.environ["DATABASE_URL"]))
    imported = 0
    for row in reader:
        if row["sku"]:
            store.add(row["sku"], row["name"], int(row["price"]))
            imported += 1
    return imported


class PriceWatcher:
    __slots__ = ("urls",)

    def __init__(self, urls):
        self.urls = urls

    def check_prices(self):
        client = ShopClient(api_key=os.environ["SHOP_KEY"], timeout=5)
        client.headers["User-Agent"] = "price-watcher"
        return [url for url in self.urls if client.price(url) < client.previous_price(url)]


def build_order_service(settings):
    return OrderService(
        ShopClient(api_key=settings.shop_key, timeout=settings.timeout),
        OrderRepository(Connection(settings.database_url)),
    )


def main():
    settings = load_settings()
    service = build_order_service(settings)
    return service.run(since=settings.since)


def parse_arguments(argv):
    parser = argparse.ArgumentParser(prog="sync")
    parser.add_argument("--since", type=int, default=0)
    return parser.parse_args(argv)


def test_sync_saves_paid_orders():
    store = InMemoryOrderStore()
    sync_orders(FakeShopClient([paid_order(), unpaid_order()]), store, since=0)
    assert store.ids() == [1]


class Settings:
    __slots__ = ("shop_key", "timeout")

    def __init__(self, shop_key, timeout):
        self.shop_key = shop_key
        self.timeout = timeout

    def create_client(self):
        return ShopClient(api_key=self.shop_key, timeout=self.timeout)
