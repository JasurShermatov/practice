"""P08: the cache as main.py wires it - SQLite file + counting SQL store + a real Redis.

- The course's four requests (Step 5 and Step 6) through the real wiring: stale without
  invalidation, fresh with it, Omar's 409 either way.
- GET /stats counts real SQL statements: 2 per search that misses (one per room), 0 per hit.
- ``build_cache``: off -> no cache, memory -> in-process, redis -> must answer PING or the app stops.
- The command line: ``--cache`` and ``--no-invalidation`` reach ``ServerOptions``.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import main
from hotel_booking.api_cache import AvailabilityCache, InMemoryKeyValueStore
from hotel_booking.api_redis import RedisKeyValueStore

from .conftest import RedisServer, free_port

PROJECT = Path(__file__).resolve().parents[1]
REQUESTS = PROJECT / "docs" / "requests"
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
BOTH_FREE = ('{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},'
             '{"number":"R8","type":"Deluxe"}],"next":null}')
ONLY_R8 = '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}'
CREATED = '{"id":"R101","status":"Confirmed","notificationFailed":false}'
UNAVAILABLE = '{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}'


def body(name: str) -> dict[str, str]:
    return json.loads((REQUESTS / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture
def redis(redis_server: RedisServer) -> RedisKeyValueStore:
    store = RedisKeyValueStore("127.0.0.1", redis_server.port)
    store.flush()  # the course's FLUSHALL: start from an empty cache
    return store


def app_over(database: Path, redis: RedisKeyValueStore, invalidation: bool = True) -> TestClient:
    cache = AvailabilityCache(redis, invalidate_on_change=invalidation)
    app, _ = main.build_api(main.sqlite_connector(database), cache=cache)
    return TestClient(app, raise_server_exceptions=False)


def four_requests(client: TestClient) -> list[tuple[int, str]]:
    answers = []
    for method, path, name in [("GET", SEARCH, None), ("POST", "/reservations", "maya-r7.json"),
                               ("GET", SEARCH, None), ("POST", "/reservations", "omar-r7.json")]:
        response = client.request(method, path, json=body(name) if name else None)
        answers.append((response.status_code, response.text))
    return answers


def test_step5_the_stale_result_through_the_real_wiring(tmp_path: Path, redis: RedisKeyValueStore) -> None:
    client = app_over(tmp_path / "hotel.sqlite3", redis, invalidation=False)
    assert four_requests(client) == [(200, BOTH_FREE), (201, CREATED), (200, BOTH_FREE), (409, UNAVAILABLE)]
    with sqlite3.connect(tmp_path / "hotel.sqlite3") as connection:  # the database knows the truth
        assert connection.execute("SELECT id, room, status FROM reservations").fetchall() == [("R101", "R7", "Confirmed")]


def test_step6_after_invalidation_the_third_answer_is_fresh(tmp_path: Path, redis: RedisKeyValueStore) -> None:
    client = app_over(tmp_path / "hotel.sqlite3", redis)
    assert four_requests(client) == [(200, BOTH_FREE), (201, CREATED), (200, ONLY_R8), (409, UNAVAILABLE)]
    assert redis.get("availability:version") == "1"


def test_stats_count_real_sql_queries(tmp_path: Path, redis: RedisKeyValueStore) -> None:
    database = tmp_path / "hotel.sqlite3"
    statements: list[str] = []
    original = main.sqlite_connector(database)

    def traced() -> sqlite3.Connection:
        connection: sqlite3.Connection = original()
        connection.set_trace_callback(statements.append)
        return connection

    app, _ = main.build_api(traced, cache=AvailabilityCache(redis))
    client = TestClient(app)
    statements.clear()
    for _ in range(10):
        client.get(SEARCH)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert client.get("/stats").json() == {"searches": 10, "databaseQueries": 2, "cacheHits": 9,
                                           "cacheMisses": 1, "cacheErrors": 0}
    assert len(selects) == 2  # the counter is the truth: two SELECTs, one per room, for ten searches


def test_build_cache_off_memory_redis(redis_server: RedisServer) -> None:
    assert main.build_cache("off") is None
    memory = main.build_cache("memory")
    assert isinstance(memory, AvailabilityCache) and memory.invalidate_on_change
    redis = main.build_cache("redis", invalidation=False,
                             redis_store=lambda: RedisKeyValueStore("127.0.0.1", redis_server.port))
    assert isinstance(redis, AvailabilityCache) and not redis.invalidate_on_change


def test_the_app_does_not_start_when_redis_does_not_answer() -> None:
    with pytest.raises(SystemExit, match="Start Redis"):
        main.build_cache("redis", redis_store=lambda: RedisKeyValueStore("127.0.0.1", free_port(), timeout_seconds=0.2))


def test_redis_address_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOTEL_REDIS_HOST", "cache.local")
    monkeypatch.setenv("HOTEL_REDIS_PORT", "16379")
    store = main.redis_from_environment()
    assert (store.host, store.port) == ("cache.local", 16379)


@pytest.mark.parametrize(("argv", "expected"), [
    (["--cache", "off"], main.ServerOptions("sqlite", 5080, "off", True)),
    (["--cache", "memory", "--port", "5081"], main.ServerOptions("sqlite", 5081, "memory", True)),
    (["--no-invalidation"], main.ServerOptions("sqlite", 5080, "redis", False)),
])
def test_cache_options_reach_the_server(argv: list[str], expected: main.ServerOptions) -> None:
    started: list[main.ServerOptions] = []
    main.main(argv, serve=started.append)
    assert started == [expected]


def test_an_unknown_cache_kind_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main.main(["--cache", "memcached"], serve=lambda options: None)
    assert "invalid choice" in capsys.readouterr().err


def test_memory_cache_through_the_wiring(tmp_path: Path) -> None:
    store = InMemoryKeyValueStore()
    app, _ = main.build_api(main.sqlite_connector(tmp_path / "h.sqlite3"), cache=AvailabilityCache(store))
    client = TestClient(app)
    assert [client.get(SEARCH).headers["X-Cache"] for _ in range(2)] == ["miss", "hit"]
    assert store.keys() == ["availability:v0:2026-11-12:2026-11-14"]
