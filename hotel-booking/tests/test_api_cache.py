"""P08: the cache through HTTP - hit, miss, expiry, invalidation, the stale result, a failing cache.

The app is built the way the wiring builds it (Stats shared by GET /stats and a counting store),
with the reservations in a list and the cache over ``InMemoryKeyValueStore`` with a fake clock.
The same behaviour over SQLite + a real Redis: tests/test_cache_wiring.py.

Also proven here, on the source: booking and cancelling never read the cache, and they raise the
version only after the unit of work (ast); the search builds its key before it asks the database.
"""
from __future__ import annotations

import ast
import inspect
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from starlette.testclient import TestClient

import hotel_booking.api as api_module
from hotel_booking.api import create_app
from hotel_booking.api_cache import TTL_SECONDS, AvailabilityCache, CacheError, InMemoryKeyValueStore
from hotel_booking.api_stats import COUNTERS, CountingReservationStore, Stats
from hotel_booking.demo import HOTEL_ROOMS, R7, nov
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, Guest, Reservation
from hotel_booking.reservations.internal import InMemoryReservationStore

SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
OMAR = {"guestName": "Omar", "guestEmail": "omar@example.com", "room": "R7", "checkIn": "2026-11-13", "checkOut": "2026-11-15"}
BOTH = ["R7", "R8"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class BrokenStore:
    """A key-value store that is down: every command fails like an unreachable Redis."""

    def __init__(self, fail_get: bool = True, fail_set: bool = True, fail_increment: bool = True) -> None:
        self.fail_get, self.fail_set, self.fail_increment = fail_get, fail_set, fail_increment
        self.inner = InMemoryKeyValueStore()

    def get(self, key: str) -> str | None:
        if self.fail_get:
            raise CacheError("connection refused")
        return self.inner.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if self.fail_set:
            raise CacheError("connection refused")
        self.inner.set(key, value, ttl_seconds)

    def increment(self, key: str) -> int:
        if self.fail_increment:
            raise CacheError("connection refused")
        return self.inner.increment(key)


@dataclass
class Hotel:
    client: TestClient
    clock: FakeClock
    store: InMemoryKeyValueStore
    reservations: InMemoryReservationStore
    units_of_work: list[str]

    def rooms(self, path: str = SEARCH) -> list[str]:
        response = self.client.get(path)
        assert response.status_code == 200, response.text
        return [room["number"] for room in response.json()["rooms"]]

    def stats(self) -> dict[str, int]:
        answer: dict[str, int] = self.client.get("/stats").json()
        return answer


def hotel(invalidate_on_change: bool = True, cache: bool = True,
          kv: InMemoryKeyValueStore | BrokenStore | None = None) -> Hotel:
    clock = FakeClock()
    store = InMemoryKeyValueStore(clock)
    stats = Stats()
    reservations = InMemoryReservationStore()
    service = BookingService(HOTEL_ROOMS, CountingReservationStore(reservations, stats), EmailNotificationSender())
    opened: list[str] = []

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        opened.append("unit of work")
        yield service

    availability = AvailabilityCache(kv or store, invalidate_on_change=invalidate_on_change) if cache else None
    client = TestClient(create_app(HOTEL_ROOMS, unit_of_work, stats, availability), raise_server_exceptions=False)
    return Hotel(client, clock, store, reservations, opened)


# --------------------------------------------------------------------------- GET /stats


def test_stats_start_at_zero() -> None:
    assert hotel().stats() == dict.fromkeys(COUNTERS, 0)


def test_without_a_cache_every_search_asks_the_database_once_per_room() -> None:
    """The "No cache" row: 2 rooms -> 2 queries per search, no hits, no misses (P07 behaviour)."""
    app = hotel(cache=False)
    for _ in range(3):
        response = app.client.get(SEARCH)
        assert response.headers["X-Cache"] == "bypass"
    assert app.stats() == {"searches": 3, "databaseQueries": 6, "cacheHits": 0, "cacheMisses": 0, "cacheErrors": 0}


def test_a_rejected_search_is_not_counted() -> None:
    app = hotel()
    app.client.get("/rooms/availability?checkIn=2026-11-14&checkOut=2026-11-12")
    assert app.stats()["searches"] == 0


def test_a_booking_costs_three_questions() -> None:
    """has_overlap + count + save (activity sheet, Step 1.4)."""
    app = hotel()
    assert app.client.post("/reservations", json=MAYA).status_code == 201
    assert app.stats()["databaseQueries"] == 3


# --------------------------------------------------------------------------- hit and miss


def test_first_search_misses_second_hits_and_asks_nobody() -> None:
    app = hotel()
    first, second = app.client.get(SEARCH), app.client.get(SEARCH)
    assert (first.headers["X-Cache"], second.headers["X-Cache"]) == ("miss", "hit")
    assert first.content == second.content  # byte for byte the same answer
    assert app.units_of_work == ["unit of work"]  # a hit opens no unit of work (no database connection)
    assert app.stats() == {"searches": 2, "databaseQueries": 2, "cacheHits": 1, "cacheMisses": 1, "cacheErrors": 0}
    assert app.store.keys() == ["availability:v0:2026-11-12:2026-11-14"]


def test_1000_searches_cost_2_queries() -> None:
    app = hotel()
    for _ in range(1000):
        app.client.get(SEARCH)
    assert app.stats() == {"searches": 1000, "databaseQueries": 2, "cacheHits": 999, "cacheMisses": 1, "cacheErrors": 0}


def test_paging_is_done_on_the_copy() -> None:
    app = hotel()
    first = app.client.get(f"{SEARCH}&limit=1").json()
    second = app.client.get(f"{SEARCH}&limit=1&after={first['next']}").json()
    assert ([room["number"] for room in first["rooms"]], first["next"]) == (["R7"], "R7")
    assert ([room["number"] for room in second["rooms"]], second["next"]) == (["R8"], None)
    assert app.stats()["cacheHits"] == 1 and app.stats()["databaseQueries"] == 2  # one copy, every page


def test_a_full_hotel_is_cached_too() -> None:
    app = hotel()
    app.client.post("/reservations", json=MAYA)
    app.client.post("/reservations", json={**MAYA, "room": "R8"})
    assert app.rooms() == [] and app.rooms() == []
    assert app.stats()["cacheHits"] == 1


# --------------------------------------------------------------------------- expiry


def test_after_30_seconds_the_copy_is_gone_and_the_search_asks_again() -> None:
    app = hotel()
    app.client.get(SEARCH)
    app.clock.now += TTL_SECONDS - 1
    assert app.client.get(SEARCH).headers["X-Cache"] == "hit"
    app.clock.now += 1
    assert app.client.get(SEARCH).headers["X-Cache"] == "miss"
    assert app.stats() == {"searches": 3, "databaseQueries": 4, "cacheHits": 1, "cacheMisses": 2, "cacheErrors": 0}


# --------------------------------------------------------------------------- invalidation and the stale result


def test_stale_result_without_invalidation_known_trade_off() -> None:
    """P08 Step 5, pinned: with invalidation switched off a search shows a booked room for up to 30 s,
    but the booking rule still holds - Omar gets 409, because booking reads the store, not the cache."""
    app = hotel(invalidate_on_change=False)
    assert app.rooms() == BOTH                                            # miss: copy "R7,R8" kept
    assert app.client.post("/reservations", json=MAYA).status_code == 201  # saved; copy untouched
    stale = app.client.get(SEARCH)
    assert stale.headers["X-Cache"] == "hit" and [r["number"] for r in stale.json()["rooms"]] == BOTH  # STALE
    omar = app.client.post("/reservations", json=OMAR)
    assert omar.status_code == 409 and omar.json()["title"] == "Unavailable"
    assert app.reservations.count_confirmed(R7, nov(12, 15)) == 1         # nobody is double-booked
    app.clock.now += TTL_SECONDS                                           # the TTL ends the stale copy
    assert app.rooms() == ["R8"]


def test_with_invalidation_the_same_four_requests_give_a_fresh_third_answer() -> None:
    app = hotel()
    assert app.rooms() == BOTH
    assert app.client.post("/reservations", json=MAYA).status_code == 201
    fresh = app.client.get(SEARCH)
    assert fresh.headers["X-Cache"] == "miss" and [r["number"] for r in fresh.json()["rooms"]] == ["R8"]
    assert app.client.post("/reservations", json=OMAR).status_code == 409
    assert app.store.get("availability:version") == "1"


def test_a_cancel_invalidates_too() -> None:
    app = hotel()
    app.client.post("/reservations", json=MAYA)
    assert app.rooms() == ["R8"]
    assert app.client.delete("/reservations/R101").status_code == 204
    assert app.rooms() == BOTH
    assert app.store.get("availability:version") == "2"


@pytest.mark.parametrize(("method", "path", "body", "status"), [
    ("POST", "/reservations", {**MAYA, "checkOut": "2026-11-12"}, 400),
    ("POST", "/reservations", {**MAYA, "room": "R99"}, 400),
    ("POST", "/reservations", "not json", 400),
    ("DELETE", "/reservations/R404", None, 404),
], ids=["invalid-dates", "unknown-room", "not-json", "cancel-unknown"])
def test_a_request_that_changes_nothing_keeps_the_version(method: str, path: str, body: object, status: int) -> None:
    app = hotel()
    app.client.get(SEARCH)
    response = app.client.request(method, path, json=body) if body != "not json" else app.client.post(path, content="x")
    assert response.status_code == status
    assert app.store.get("availability:version") is None
    assert app.client.get(SEARCH).headers["X-Cache"] == "hit"


def test_a_409_keeps_the_version() -> None:
    app = hotel()
    app.client.post("/reservations", json=MAYA)  # version 1
    assert app.client.post("/reservations", json=OMAR).status_code == 409
    assert app.store.get("availability:version") == "1"


def test_versions_leave_old_copies_to_expire_by_themselves() -> None:
    app = hotel()
    app.client.get(SEARCH)
    app.client.post("/reservations", json=MAYA)
    app.client.get(SEARCH)
    assert app.store.keys() == ["availability:v0:2026-11-12:2026-11-14", "availability:v1:2026-11-12:2026-11-14",
                                "availability:version"]
    app.clock.now += TTL_SECONDS
    assert app.store.keys() == ["availability:version"]


# --------------------------------------------------------------------------- a failing cache never fails a request


def test_cache_down_the_search_answers_from_the_database() -> None:
    app = hotel(kv=BrokenStore())
    response = app.client.get(SEARCH)
    assert response.status_code == 200 and response.headers["X-Cache"] == "bypass"
    assert [room["number"] for room in response.json()["rooms"]] == BOTH
    assert app.stats() == {"searches": 1, "databaseQueries": 2, "cacheHits": 0, "cacheMisses": 0, "cacheErrors": 1}


def test_cache_down_a_booking_is_still_answered_201_and_saved() -> None:
    app = hotel(kv=BrokenStore())
    response = app.client.post("/reservations", json=MAYA)
    assert response.status_code == 201 and response.json()["id"] == "R101"
    assert app.reservations.find("R101") is not None
    assert app.stats()["cacheErrors"] == 1  # the INCR failed and was counted


def test_a_failing_put_still_answers_the_search() -> None:
    app = hotel(kv=BrokenStore(fail_get=False, fail_set=True, fail_increment=False))
    assert [app.client.get(SEARCH).headers["X-Cache"] for _ in range(2)] == ["miss", "miss"]
    assert app.stats()["cacheErrors"] == 2


def test_the_server_logs_a_cache_failure(caplog: pytest.LogCaptureFixture) -> None:
    hotel(kv=BrokenStore()).client.get(SEARCH)
    assert "cache lookup failed, going on without the cache: connection refused" in caplog.text


# --------------------------------------------------------------------------- the counters and the counting store


def test_the_counting_store_counts_every_promised_call_and_passes_it_on() -> None:
    stats, inner = Stats(), InMemoryReservationStore()
    store = CountingReservationStore(inner, stats)
    reservation = Reservation("R101", Guest("Maya", "maya@example.com"), R7, nov(12, 14))
    store.save(reservation)
    assert store.count() == 1 and store.find("R101") is reservation
    assert store.has_overlap(R7, nov(13, 15)) and store.count_confirmed(R7, nov(12, 14)) == 1
    assert stats.snapshot()["databaseQueries"] == 5 and inner.count() == 1


def test_counters_are_exact_under_threads() -> None:
    stats = Stats()

    def add() -> None:
        for _ in range(10_000):
            stats.add("searches")

    threads = [threading.Thread(target=add) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert stats.snapshot()["searches"] == 80_000


# --------------------------------------------------------------------------- on the source: booking never reads the cache


def endpoint(name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(inspect.getsource(api_module))
    return next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == name)


def called(function: ast.AST) -> list[tuple[int, str]]:
    return sorted((node.lineno, ast.unparse(node.func)) for node in ast.walk(function) if isinstance(node, ast.Call))


@pytest.mark.parametrize("name", ["reserve", "cancel"])
def test_booking_and_cancelling_never_read_the_cache(name: str) -> None:
    calls = [call for _, call in called(endpoint(name))]
    assert "invalidate_cache" in calls
    assert not {"search_free_rooms", "cache.lookup", "cache.key", "cache.put"} & set(calls)
    assert "cache.lookup" not in ast.unparse(endpoint(name))


@pytest.mark.parametrize("name", ["reserve", "cancel"])
def test_the_version_is_raised_after_the_unit_of_work(name: str) -> None:
    calls = called(endpoint(name))
    work = min(line for line, call in calls if call == "in_unit_of_work")
    invalidate = min(line for line, call in calls if call == "invalidate_cache")
    assert work < invalidate


def test_the_search_builds_its_key_before_it_asks_the_database() -> None:
    calls = called(endpoint("search_free_rooms"))
    lookup = min(line for line, call in calls if call == "run_in_threadpool")
    database = [line for line, call in calls if call == "in_unit_of_work"]
    assert "cache.lookup" in ast.unparse(endpoint("search_free_rooms"))
    assert lookup < max(database)
