import pytest

from shop.cart import Cart


@pytest.fixture
def empty_cart():
    return Cart(items=[])


def test_empty_cart_has_zero_total(empty_cart):
    assert empty_cart.total() == 0


def test_cart_counts_added_items():
    cart = Cart(items=[])
    cart.add("apple", 2)
    assert cart.count() == 2
