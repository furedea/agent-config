import pytest

from shop.pricing import apply_discount


@pytest.fixture(scope="session")
def discount_rates():
    return {"member": 0.1, "staff": 0.3}


def test_member_discount_reduces_the_price(discount_rates):
    assert apply_discount(1000, discount_rates["member"]) == 900


def test_zero_discount_keeps_the_price():
    assert apply_discount(1000, 0.0) == 1000
