import pytest

from shop.clock import FrozenClock


@pytest.fixture
def frozen_clock():
    return FrozenClock(at="2026-01-01T00:00:00Z")
