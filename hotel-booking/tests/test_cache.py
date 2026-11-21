"""P08: the availability cache on its own - key, value, TTL, version and the in-memory store.

The store gets a fake clock, so expiry is tested by moving time forward, not by sleeping 30 s.
The same promise on a real Redis: tests/test_redis_store.py.
"""
from __future__ import annotations

from datetime import date

import pytest

from hotel_booking.api_cache import (
    TTL_SECONDS,
    VERSION_KEY,
    AvailabilityCache,
    InMemoryKeyValueStore,
    decode,
    encode,
)

NOV_12, NOV_14 = date(2026, 11, 12), date(2026, 11, 14)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class RecordingStore(InMemoryKeyValueStore):
    """Remembers every SET's TTL, to prove the cache asks for 30 seconds."""

    def __init__(self) -> None:
        super().__init__()
        self.ttls: list[tuple[str, int]] = []

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.ttls.append((key, ttl_seconds))
        super().set(key, value, ttl_seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def cache(clock: FakeClock) -> AvailabilityCache:
    return AvailabilityCache(InMemoryKeyValueStore(clock))


# --------------------------------------------------------------------------- the four decisions


def test_the_key_is_version_and_stay_and_the_version_starts_at_0(cache: AvailabilityCache) -> None:
    assert cache.key(NOV_12, NOV_14) == "availability:v0:2026-11-12:2026-11-14"
    assert cache.version() == 0


def test_a_copy_is_kept_for_30_seconds() -> None:
    store = RecordingStore()
    cache = AvailabilityCache(store)
    cache.put(cache.key(NOV_12, NOV_14), ["R8", "R7"])
    assert store.ttls == [("availability:v0:2026-11-12:2026-11-14", 30)] and TTL_SECONDS == 30
    assert store.get("availability:v0:2026-11-12:2026-11-14") == "R7,R8"  # text order


def test_miss_then_hit(cache: AvailabilityCache) -> None:
    key, numbers = cache.lookup(NOV_12, NOV_14)
    assert numbers is None
    cache.put(key, ["R7", "R8"])
    assert cache.lookup(NOV_12, NOV_14) == (key, ["R7", "R8"])


def test_no_free_room_is_an_answer_too(cache: AvailabilityCache) -> None:
    key, _ = cache.lookup(NOV_12, NOV_14)
    cache.put(key, [])
    assert cache.lookup(NOV_12, NOV_14) == (key, [])  # a hit with no rooms, not a miss


def test_one_copy_per_stay(cache: AvailabilityCache) -> None:
    cache.put(cache.key(NOV_12, NOV_14), ["R7", "R8"])
    assert cache.lookup(NOV_12, date(2026, 11, 15))[1] is None


# --------------------------------------------------------------------------- expiry (TTL)


def test_the_copy_expires_after_the_ttl(cache: AvailabilityCache, clock: FakeClock) -> None:
    key, _ = cache.lookup(NOV_12, NOV_14)
    cache.put(key, ["R7", "R8"])
    clock.now += 29.9
    assert cache.lookup(NOV_12, NOV_14)[1] == ["R7", "R8"]
    clock.now += 0.1  # exactly 30 s after the SET
    assert cache.lookup(NOV_12, NOV_14)[1] is None


def test_a_shorter_ttl_can_be_chosen_but_not_zero(clock: FakeClock) -> None:
    cache = AvailabilityCache(InMemoryKeyValueStore(clock), ttl_seconds=5)
    cache.put(cache.key(NOV_12, NOV_14), ["R7"])
    clock.now += 5
    assert cache.lookup(NOV_12, NOV_14)[1] is None
    with pytest.raises(ValueError):
        AvailabilityCache(InMemoryKeyValueStore(), ttl_seconds=0)


# --------------------------------------------------------------------------- invalidation (version)


def test_invalidate_raises_the_version_and_older_copies_are_no_longer_read(cache: AvailabilityCache) -> None:
    cache.put(cache.key(NOV_12, NOV_14), ["R7", "R8"])
    cache.invalidate()
    assert cache.version() == 1
    key, numbers = cache.lookup(NOV_12, NOV_14)
    assert key == "availability:v1:2026-11-12:2026-11-14" and numbers is None


def test_an_answer_read_before_a_booking_is_stored_under_the_old_version(cache: AvailabilityCache) -> None:
    """The key is built before the database is asked: a booking in between cannot leave a stale copy.

    search: lookup (key v0, miss) -> reads the database -> [booking commits, INCR -> v1] -> put(v0 key)
    """
    key, _ = cache.lookup(NOV_12, NOV_14)  # the search builds its key
    cache.invalidate()                      # a booking commits meanwhile
    cache.put(key, ["R7", "R8"])            # the search stores what it read before the booking
    assert cache.lookup(NOV_12, NOV_14)[1] is None  # nobody reads that copy: the next search misses


def test_without_invalidation_the_old_copy_stays_readable(clock: FakeClock) -> None:
    """The Step 5 experiment switch: invalidate() does nothing, so only the TTL ends a stale copy."""
    store = InMemoryKeyValueStore(clock)
    cache = AvailabilityCache(store, invalidate_on_change=False)
    cache.put(cache.key(NOV_12, NOV_14), ["R7", "R8"])
    cache.invalidate()
    assert store.get(VERSION_KEY) is None
    assert cache.lookup(NOV_12, NOV_14)[1] == ["R7", "R8"]
    clock.now += TTL_SECONDS
    assert cache.lookup(NOV_12, NOV_14)[1] is None


# --------------------------------------------------------------------------- the in-memory store and the value


def test_increment_counts_from_zero_and_keeps_a_ttl(clock: FakeClock) -> None:
    store = InMemoryKeyValueStore(clock)
    assert [store.increment("n"), store.increment("n")] == [1, 2]
    store.set("t", "5", 10)
    assert store.increment("t") == 6
    clock.now += 10
    assert store.get("t") is None  # INCR did not remove the TTL (as in Redis)


def test_keys_lists_only_live_keys(clock: FakeClock) -> None:
    store = InMemoryKeyValueStore(clock)
    store.set("availability:v0:a", "R7", 30)
    store.set("availability:v0:b", "R8", 60)
    clock.now += 30
    assert store.keys() == ["availability:v0:b"]


@pytest.mark.parametrize("numbers", [[], ["R7"], ["R10", "R7", "R8"]])
def test_value_round_trip_in_text_order(numbers: list[str]) -> None:
    assert decode(encode(numbers)) == sorted(numbers)


def test_a_room_number_that_would_break_the_value_is_refused() -> None:
    with pytest.raises(ValueError):
        encode(["R7,R8"])
    with pytest.raises(ValueError):
        encode([""])
