import pytest

from shop.cart import Cart, Item


@pytest.fixture
def cart_with_apples():
    return Cart(items=[Item("apple", price=120, quantity=3)])


def test_total_multiplies_price_by_quantity(cart_with_apples):
    assert cart_with_apples.total() == 360


def test_removing_the_only_item_empties_the_cart(cart_with_apples):
    cart_with_apples.remove("apple")
    assert cart_with_apples.count() == 0
