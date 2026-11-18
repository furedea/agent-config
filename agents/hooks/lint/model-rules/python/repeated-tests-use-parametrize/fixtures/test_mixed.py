import pytest

from shop.money import Money


def test_money_adds_amounts():
    assert Money(100, "EUR") + Money(50, "EUR") == Money(150, "EUR")


def test_money_formats_euros():
    assert str(Money(1250, "EUR")) == "12.50 EUR"


def test_money_formats_yen():
    assert str(Money(1250, "JPY")) == "1250 JPY"


def test_money_formats_dollars():
    assert str(Money(1250, "USD")) == "12.50 USD"


def test_money_rejects_mixed_currencies():
    with pytest.raises(ValueError, match="cannot add"):
        Money(100, "EUR") + Money(100, "USD")
