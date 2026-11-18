from shop.durations import parse_duration


def test_parse_duration_reads_minutes():
    seconds = parse_duration("5m")
    assert seconds == 300


def test_parse_duration_reads_hours():
    seconds = parse_duration("2h")
    assert seconds == 7200
