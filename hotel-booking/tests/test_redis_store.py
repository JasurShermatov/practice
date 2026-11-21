"""P08: the Redis adapter - the RESP2 wire format, and the three commands against a real redis-server.

The integration tests use the ``redis_server`` fixture (tests/conftest.py): a throw-away
redis-server on a free port, skipped where Redis is not installed. They prove that
``RedisKeyValueStore`` keeps the same ``KeyValueStore`` promise as the in-memory store - including
a real expiry - and that every failure becomes ``CacheError`` (which the API survives).
"""
from __future__ import annotations

import io
import socket
import time
from datetime import date

import pytest

from hotel_booking.api_cache import AvailabilityCache, CacheError
from hotel_booking.api_redis import RedisKeyValueStore, RedisReplyError, encode_command, read_reply

from .conftest import RedisServer, free_port

NOV_12, NOV_14 = date(2026, 11, 12), date(2026, 11, 14)


# --------------------------------------------------------------------------- the wire format


def test_a_command_is_an_array_of_bulk_strings() -> None:
    assert encode_command(("SET", "k", "R7,R8", "EX", "30")) == (
        b"*5\r\n$3\r\nSET\r\n$1\r\nk\r\n$5\r\nR7,R8\r\n$2\r\nEX\r\n$2\r\n30\r\n")
    assert encode_command(("GET", "ä")) == b"*2\r\n$3\r\nGET\r\n$2\r\n\xc3\xa4\r\n"  # length in bytes


@pytest.mark.parametrize(("wire", "reply"), [
    (b"+OK\r\n", "OK"),
    (b":42\r\n", 42),
    (b"$5\r\nR7,R8\r\n", "R7,R8"),
    (b"$0\r\n\r\n", ""),
    (b"$-1\r\n", None),
    (b"*2\r\n$1\r\na\r\n:1\r\n", ["a", 1]),
    (b"*-1\r\n", None),
])
def test_every_reply_type_is_read(wire: bytes, reply: object) -> None:
    assert read_reply(io.BytesIO(wire)) == reply


@pytest.mark.parametrize("wire", [b"", b"$5\r\nR7", b"?what\r\n"], ids=["closed", "cut-short", "unknown"])
def test_a_broken_reply_is_a_cache_error(wire: bytes) -> None:
    with pytest.raises(CacheError):
        read_reply(io.BytesIO(wire))


def test_an_error_reply_is_its_own_kind() -> None:
    with pytest.raises(RedisReplyError, match="WRONGTYPE"):
        read_reply(io.BytesIO(b"-WRONGTYPE Operation against a key\r\n"))


# --------------------------------------------------------------------------- against a real redis-server


@pytest.fixture
def redis(redis_server: RedisServer) -> RedisKeyValueStore:
    store = RedisKeyValueStore("127.0.0.1", redis_server.port)
    store.flush()
    return store


def test_ping_get_set_increment(redis: RedisKeyValueStore) -> None:
    redis.ping()
    assert redis.get("availability:v0:2026-11-12:2026-11-14") is None
    redis.set("availability:v0:2026-11-12:2026-11-14", "R7,R8", 30)
    assert redis.get("availability:v0:2026-11-12:2026-11-14") == "R7,R8"
    assert [redis.increment("availability:version"), redis.increment("availability:version")] == [1, 2]
    assert redis.get("availability:version") == "2"


def test_redis_itself_expires_the_copy(redis: RedisKeyValueStore) -> None:
    redis.set("short", "R7", 1)
    assert redis.get("short") == "R7"
    time.sleep(1.2)
    assert redis.get("short") is None


def test_the_ttl_is_sent_as_ex_seconds(redis: RedisKeyValueStore, redis_server: RedisServer) -> None:
    AvailabilityCache(redis).put("availability:v0:2026-11-12:2026-11-14", ["R7", "R8"])
    with socket.create_connection(("127.0.0.1", redis_server.port)) as raw:
        raw.sendall(encode_command(("TTL", "availability:v0:2026-11-12:2026-11-14")))
        ttl = read_reply(raw.makefile("rb"))
    assert isinstance(ttl, int) and 28 <= ttl <= 30


def test_the_cache_on_redis_hit_miss_and_version(redis: RedisKeyValueStore) -> None:
    cache = AvailabilityCache(redis)
    key, numbers = cache.lookup(NOV_12, NOV_14)
    assert (key, numbers) == ("availability:v0:2026-11-12:2026-11-14", None)
    cache.put(key, ["R8", "R7"])
    assert cache.lookup(NOV_12, NOV_14)[1] == ["R7", "R8"]
    cache.invalidate()
    assert cache.lookup(NOV_12, NOV_14) == ("availability:v1:2026-11-12:2026-11-14", None)


def test_an_error_reply_keeps_the_connection_usable(redis: RedisKeyValueStore) -> None:
    redis.set("text", "R7", 30)
    with pytest.raises(CacheError, match="not an integer"):
        redis.increment("text")
    assert redis.get("text") == "R7"


def test_connections_are_reused(redis: RedisKeyValueStore, redis_server: RedisServer) -> None:
    for _ in range(50):
        redis.get("x")
    with socket.create_connection(("127.0.0.1", redis_server.port)) as raw:
        raw.sendall(encode_command(("CLIENT", "LIST")))
        clients = read_reply(raw.makefile("rb"))
    assert isinstance(clients, str) and clients.count("cmd=get") == 1  # one pooled connection did all 50


def test_nobody_listening_is_a_cache_error_quickly() -> None:
    store = RedisKeyValueStore("127.0.0.1", free_port(), timeout_seconds=0.2)
    started = time.monotonic()
    with pytest.raises(CacheError, match="cannot connect to Redis"):
        store.get("x")
    with pytest.raises(CacheError):
        store.ping()
    assert time.monotonic() - started < 1.0


def test_redis_stopping_and_starting_again(tmp_path_factory: pytest.TempPathFactory) -> None:
    """An outage: commands fail with CacheError; after the restart the same store works again.

    Redis keeps no data here (no volume, no persistence): the version starts at 0 again, and the
    old copies are gone too - so no stale copy survives a restart.
    """
    server = RedisServer(free_port(), tmp_path_factory.mktemp("redis-outage"))
    server.start()
    store = RedisKeyValueStore("127.0.0.1", server.port)
    try:
        store.set("availability:v1:x", "R7", 30)
        store.increment("availability:version")
        server.stop()
        with pytest.raises(CacheError):
            store.get("availability:version")  # the pooled connection is dead: thrown away
        server.start()
        assert store.get("availability:version") is None and store.get("availability:v1:x") is None
        store.set("availability:v0:x", "R8", 30)
        assert store.get("availability:v0:x") == "R8"
    finally:
        store.close()
        server.stop()
