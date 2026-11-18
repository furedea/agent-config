import pytest

from shop.money import Money


@pytest.fixture
def ten_euros():
    return Money(1000, "EUR")


def test_money_adds_amounts_of_one_currency():
    assert Money(1000, "EUR") + Money(500, "EUR") == Money(1500, "EUR")
