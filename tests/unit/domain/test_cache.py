import threading

import pytest

from small_service.domain.cache import TimedCache
from small_service.domain.errors import InvalidTtlError
from tests.unit.fakes import FakeClock


def make_cache(ttl: float = 10.0) -> tuple[TimedCache[str, int], FakeClock]:
    clock = FakeClock()
    return TimedCache(ttl, clock), clock


def test_a_stored_value_is_returned_before_it_expires():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(9.9)
    assert cache.get("a") == 1


def test_a_value_expires_exactly_at_its_time_to_live():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(10)
    assert cache.get("a") is None


def test_reading_an_expired_value_drops_it():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(11)
    cache.get("a")
    assert len(cache) == 0


def test_a_missing_key_returns_none():
    cache, _ = make_cache()
    assert cache.get("nothing") is None


def test_putting_again_restarts_the_time_to_live():
    cache, clock = make_cache()
    cache.put("a", 1)
    clock.advance(8)
    cache.put("a", 2)
    clock.advance(8)
    assert cache.get("a") == 2


def test_purge_drops_only_expired_entries_and_counts_them():
    cache, clock = make_cache()
    cache.put("old", 1)
    clock.advance(6)
    cache.put("new", 2)
    clock.advance(5)
    assert cache.purge() == 1
    assert cache.get("new") == 2


@pytest.mark.parametrize("ttl", [0, -1, -0.5])
def test_a_non_positive_time_to_live_is_refused(ttl):
    with pytest.raises(InvalidTtlError):
        TimedCache(ttl, FakeClock())


def test_concurrent_puts_do_not_lose_entries():
    cache, _ = make_cache()
    threads = [threading.Thread(target=cache.put, args=(f"key-{index}", index)) for index in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(cache) == 50
