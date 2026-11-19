import sqlite3

import pytest

from shop.storage import OrderStore


@pytest.fixture
def order_store(tmp_path):
    connection = sqlite3.connect(tmp_path / "orders.db")
    yield OrderStore(connection)
    connection.close()


def test_saved_order_can_be_loaded(order_store):
    order_store.save(order_id=7, total=500)
    assert order_store.load(7).total == 500
