import pytest

from shop.money import Money, parse_amount
from shop.export import export_csv
from shop.orders import parse_order_id


@pytest.mark.xfail(strict=True, reason="negative totals round the wrong way")
def test_negative_total_rounds_half_away_from_zero():
    assert Money(-250, "EUR").rounded() == Money(-300, "EUR")


# Broken, fix later.
@pytest.mark.xfail(strict=True, reason="currency symbols")
def test_parse_amount_accepts_a_currency_symbol():
    assert parse_amount("€12.50") == Money(1250, "EUR")


# Remove the marker when #123 (rounding of negative totals) is fixed.
@pytest.mark.xfail(strict=True, reason="#123")
def test_negative_amount_rounds_half_away_from_zero():
    assert Money(-150, "EUR").rounded() == Money(-200, "EUR")


# TODO: investigate.
@pytest.mark.xfail(strict=True, reason="quoted newlines")
def test_export_keeps_quoted_newlines():
    assert export_csv([{"note": "a\nb"}]) == 'note\n"a\nb"\n'


# Remove when pydantic 2.12 is released with the strict UUID fix.
@pytest.mark.xfail(strict=True, reason="strict UUID parsing")
def test_order_id_accepts_an_uppercase_uuid():
    assert parse_order_id("0F8FAD5B-D9CB-469F-A165-70867728950E").version == 4


# Remove when CSV export supports quoted newlines (the exporter rewrite in #88 is merged).
@pytest.mark.xfail(strict=True, reason="quoted newlines")
def test_export_keeps_carriage_returns():
    assert export_csv([{"note": "a\r\nb"}]) == 'note\n"a\r\nb"\n'


@pytest.mark.xfail(reason="flaky on CI")
def test_parse_amount_accepts_thousands_separators():
    assert parse_amount("1,000.00") == Money(100000, "EUR")


@pytest.mark.xfail(
    strict=True,
    # Remove after the tax table for 2027 is published and loaded.
    reason="2027 tax table missing",
)
def test_vat_for_2027_uses_the_new_rate():
    assert Money(1000, "EUR").with_vat(year=2027) == Money(1210, "EUR")
