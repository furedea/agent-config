from shop.text import slugify


def test_slugify_lowercases():
    assert slugify("Hello") == "hello"


def test_slugify_replaces_spaces():
    assert slugify("hello world") == "hello-world"


def test_slugify_strips_punctuation():
    assert slugify("hello, world!") == "hello-world"
