"""The cache for the free-room search (P08 Step 3): cache-aside with a TTL and a version.

The database is the source of truth. The cache keeps *copies* of search answers - the free room
numbers for one stay, such as ``"R7,R8"`` - for ``TTL_SECONDS``. Only the search reads it;
booking and cancelling never do (ADR-002): a stale copy may mislead a guest for a moment, it can
never decide a booking.

The four decisions (P08 Step 3):

- Key: ``availability:v{version}:{checkIn}:{checkOut}`` - one copy per stay; raising the version
  makes every older copy unreachable at once (Step 6).
- Value: the free room numbers in text order, ``"R7,R8"`` - small; the API rebuilds the rooms
  from the room list it already has.
- TTL: 30 seconds (``SET ... EX 30``) - a copy that is ever wrong is wrong for at most 30 s.
- What is cached: only GET /rooms/availability - booking and cancelling read the database.

The cache needs three commands of a key-value store - GET, SET with a time to live, INCR - behind
the small ``KeyValueStore`` promise. The wiring plugs in Redis (``api_redis.RedisKeyValueStore``)
or, without Redis, ``InMemoryKeyValueStore`` (one process only); the tests use the in-memory store
with a fake clock, so the real key, version and expiry code runs without Redis.

This file knows no module of the app (``.importlinter``: "The availability cache depends on no
module"): it stores text and knows nothing about rooms or reservations.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol

TTL_SECONDS = 30
VERSION_KEY = "availability:version"
KEY_PREFIX = "availability"
SEPARATOR = ","


class CacheError(Exception):
    """A cache command failed (store down, timeout, unexpected reply). The API goes on without it."""


class KeyValueStore(Protocol):
    """The three commands the cache uses. Implementations raise ``CacheError`` when they fail."""

    def get(self, key: str) -> str | None:
        """The value under ``key``, or None when there is none (never set, or expired)."""
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Keep ``value`` under ``key`` for ``ttl_seconds`` (Redis: ``SET key value EX ttl``)."""
        ...

    def increment(self, key: str) -> int:
        """Add 1 to the whole number under ``key`` (a missing key counts as 0); the new number."""
        ...


class AvailabilityCache:
    """Copies of search answers: the free room numbers for one stay, under a versioned key."""

    def __init__(self, store: KeyValueStore, *, ttl_seconds: int = TTL_SECONDS,
                 invalidate_on_change: bool = True) -> None:
        """``invalidate_on_change=False`` exists for one experiment only: P08 Step 5 (the stale result)."""
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be at least 1")
        self._store = store
        self.ttl_seconds = ttl_seconds
        self.invalidate_on_change = invalidate_on_change

    def version(self) -> int:
        """The current version (0 until the first booking or cancel raised it)."""
        return int(self._store.get(VERSION_KEY) or "0")

    def key(self, check_in: date, check_out: date) -> str:
        # The version is part of the key, so raising it makes every older copy unreachable.
        return f"{KEY_PREFIX}:v{self.version()}:{check_in.isoformat()}:{check_out.isoformat()}"

    def lookup(self, check_in: date, check_out: date) -> tuple[str, list[str] | None]:
        """The key for this stay and the cached room numbers (None on a miss).

        The key is built *before* the database is asked on a miss: if a booking raises the version
        in between, the answer read before it is stored under the old, unreachable version.
        """
        key = self.key(check_in, check_out)
        value = self._store.get(key)
        return key, None if value is None else decode(value)

    def put(self, key: str, room_numbers: Iterable[str]) -> None:
        """Keep a copy of a search answer for ``ttl_seconds``."""
        self._store.set(key, encode(room_numbers), self.ttl_seconds)

    def invalidate(self) -> None:
        """A booking or a cancel changed what is free: every cached search is now out of date.

        Called by the API *after* the unit of work committed. Raising one number is cheaper and
        safer than finding every stay that overlaps the changed one; the old copies expire alone.
        """
        if self.invalidate_on_change:
            self._store.increment(VERSION_KEY)


def encode(room_numbers: Iterable[str]) -> str:
    numbers = sorted(room_numbers)
    if any(SEPARATOR in number or not number for number in numbers):
        raise ValueError(f"room numbers must be non-empty and contain no {SEPARATOR!r}: {numbers}")
    return SEPARATOR.join(numbers)


def decode(value: str) -> list[str]:
    return value.split(SEPARATOR) if value else []  # "" is a real answer: no room is free


class InMemoryKeyValueStore:
    """The three commands on a dictionary, with real expiry. For tests and ``--cache memory``.

    One process only: two app instances would each have their own copies and their own version,
    so a booking on one instance would not invalidate the other (that is why the course uses Redis).
    ``clock`` is injectable so tests can move time forward instead of sleeping 30 seconds.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._values: dict[str, tuple[str, float | None]] = {}  # key -> (value, expires at)

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._live(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._values[key] = (value, self._clock() + ttl_seconds)

    def increment(self, key: str) -> int:
        with self._lock:
            current = self._live(key)
            expires = self._values[key][1] if current is not None else None  # INCR keeps a TTL
            number = int(current or "0") + 1
            self._values[key] = (str(number), expires)
            return number

    def keys(self) -> list[str]:
        """The live keys, sorted (like ``redis-cli KEYS "availability:*"``)."""
        with self._lock:
            return sorted(key for key in list(self._values) if self._live(key) is not None)

    def _live(self, key: str) -> str | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires is not None and self._clock() >= expires:
            del self._values[key]  # expired: gone, as in Redis
            return None
        return value
