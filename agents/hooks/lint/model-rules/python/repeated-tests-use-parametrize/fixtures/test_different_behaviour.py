import pytest

from shop.cart import Cart, Item


def test_new_cart_is_empty():
    assert Cart().count() == 0


def test_adding_an_item_increases_the_total():
    cart = Cart()
    cart.add(Item("apple", price=120, quantity=2))
    assert cart.total() == 240


def test_adding_a_negative_quantity_is_rejected():
    with pytest.raises(ValueError, match="quantity must be positive"):
        Cart().add(Item("apple", price=120, quantity=-1))
