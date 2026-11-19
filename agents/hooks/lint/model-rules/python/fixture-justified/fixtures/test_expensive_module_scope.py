import pytest

from shop.search import SearchIndex


@pytest.fixture(scope="module")
def product_index():
    index = SearchIndex()
    index.build_from_dump("tests/data/products-200k.jsonl")
    return index


def test_search_finds_exact_name(product_index):
    assert product_index.search("green tea")[0].name == "green tea"


def test_search_ignores_case(product_index):
    assert product_index.search("GREEN TEA")[0].name == "green tea"
