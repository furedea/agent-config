import pytest

from shop.cart import Cart, Item


@pytest.fixture
def cart_of_three():
    return Cart(items=[Item("pear", price=80, quantity=3)])


def test_cart_of_three_counts_three(cart_of_three):
    assert cart_of_three.count() == 3


def test_cart_of_five_counts_five():
    cart = Cart(items=[Item("pear", price=80, quantity=5)])
    assert cart.count() == 5


def test_cart_of_zero_counts_zero():
    cart = Cart(items=[Item("pear", price=80, quantity=0)])
    assert cart.count() == 0
