import pytest

from shop.durations import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("5m", 300), ("2h", 7200), ("1d", 86400)],
)
def test_parse_duration_reads_each_unit(text, seconds):
    assert parse_duration(text) == seconds


def test_parse_duration_rejects_a_missing_unit():
    with pytest.raises(ValueError, match="missing unit"):
        parse_duration("5")
