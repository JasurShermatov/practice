"""The cache's three commands, sent to Redis (P08 Step 3) - over the Redis protocol, standard library only.

The course's Python reference uses the ``redis`` package (redis-py). It cannot be installed in the
environment this portfolio is built in (no PyPI), so this file speaks RESP2 - Redis's wire
protocol - itself: a command is an array of bulk strings, a reply is one of five typed lines.
The cache needs only five commands (PING, GET, SET ... EX, INCR, and FLUSHDB for tools), so the
client stays small. It keeps the ``KeyValueStore`` promise of ``api_cache``; swapping in redis-py
later changes this file only.

Robustness, because the cache must never take the booking rule down with it:

- every socket has a timeout (``timeout_seconds``), so a stuck Redis cannot hang a request;
- any failure (refused connection, timeout, closed socket, error reply) becomes ``CacheError``,
  and the connection that failed is thrown away instead of being reused half-read;
- connections are pooled (one per concurrent request at most, kept for reuse), so requests on
  Starlette's worker threads never share a socket.
"""
from __future__ import annotations

import queue
import socket
from typing import BinaryIO

from hotel_booking.api_cache import CacheError

Reply = str | int | None | list["Reply"]

DEFAULT_TIMEOUT_SECONDS = 0.5
DEFAULT_POOL_SIZE = 16


class RedisReplyError(CacheError):
    """Redis answered with an error line (``-ERR ...``); the connection itself is still fine."""


class _Connection:
    """One TCP connection to Redis with a buffered reader."""

    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self._socket = socket.create_connection((host, port), timeout=timeout_seconds)
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._reader: BinaryIO = self._socket.makefile("rb")

    def command(self, *parts: str) -> Reply:
        self._socket.sendall(encode_command(parts))
        return read_reply(self._reader)

    def close(self) -> None:
        self._reader.close()
        self._socket.close()


def encode_command(parts: tuple[str, ...]) -> bytes:
    """``("SET", "k", "v")`` -> ``*3\\r\\n$3\\r\\nSET\\r\\n$1\\r\\nk\\r\\n$1\\r\\nv\\r\\n`` (RESP2 array of bulk strings)."""
    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        data = part.encode("utf-8")
        chunks.append(b"$%d\r\n%s\r\n" % (len(data), data))
    return b"".join(chunks)


def read_reply(reader: BinaryIO) -> Reply:
    """Read one RESP2 reply: +simple, -error, :integer, $bulk (or $-1 = nil), *array."""
    line = reader.readline()
    if not line.endswith(b"\r\n"):
        raise CacheError("Redis closed the connection")
    kind, rest = line[:1], line[1:-2].decode("utf-8")
    if kind == b"+":
        return rest
    if kind == b"-":
        raise RedisReplyError(f"Redis answered an error: {rest}")
    if kind == b":":
        return int(rest)
    if kind == b"$":
        length = int(rest)
        if length < 0:
            return None
        data = reader.read(length + 2)
        if len(data) != length + 2:
            raise CacheError("Redis closed the connection in the middle of a reply")
        return data[:-2].decode("utf-8")
    if kind == b"*":
        count = int(rest)
        return None if count < 0 else [read_reply(reader) for _ in range(count)]
    raise CacheError(f"unexpected reply from Redis: {line!r}")


class RedisKeyValueStore:
    """GET, SET ... EX and INCR, sent to one Redis server (``docker compose``: localhost:6379)."""

    def __init__(self, host: str = "localhost", port: int = 6379, *,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, pool_size: int = DEFAULT_POOL_SIZE) -> None:
        self.host, self.port = host, port
        self._timeout = timeout_seconds
        self._idle: queue.LifoQueue[_Connection] = queue.LifoQueue(maxsize=pool_size)

    # ------------------------------------------------------------------ the KeyValueStore promise

    def get(self, key: str) -> str | None:
        reply = self._command("GET", key)
        if reply is not None and not isinstance(reply, str):
            raise CacheError(f"GET {key} answered {reply!r}")
        return reply

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._expect_ok(self._command("SET", key, value, "EX", str(ttl_seconds)), "SET")

    def increment(self, key: str) -> int:
        reply = self._command("INCR", key)
        if not isinstance(reply, int):
            raise CacheError(f"INCR {key} answered {reply!r}")
        return reply

    # ------------------------------------------------------------------ for the wiring and tools

    def ping(self) -> None:
        """Raise ``CacheError`` unless Redis answers PONG (the wiring calls it once at start-up)."""
        reply = self._command("PING")
        if reply != "PONG":
            raise CacheError(f"PING answered {reply!r}")

    def flush(self) -> None:
        """FLUSHDB: delete every key of this database (tests and experiments only, never the app)."""
        self._expect_ok(self._command("FLUSHDB"), "FLUSHDB")

    def close(self) -> None:
        while True:
            try:
                self._idle.get_nowait().close()
            except queue.Empty:
                return

    # ------------------------------------------------------------------ internals

    def _command(self, *parts: str) -> Reply:
        try:
            connection = self._idle.get_nowait()
        except queue.Empty:
            try:
                connection = _Connection(self.host, self.port, self._timeout)
            except OSError as error:
                raise CacheError(f"cannot connect to Redis at {self.host}:{self.port}: {error}") from error
        try:
            reply = connection.command(*parts)
        except RedisReplyError:
            self._give_back(connection)  # the whole error line was read: the connection is clean
            raise
        except CacheError:
            connection.close()  # closed or half-read: never reuse it
            raise
        except (OSError, ValueError) as error:
            connection.close()
            raise CacheError(f"Redis at {self.host}:{self.port} failed: {error}") from error
        self._give_back(connection)
        return reply

    def _give_back(self, connection: _Connection) -> None:
        try:
            self._idle.put_nowait(connection)
        except queue.Full:
            connection.close()

    @staticmethod
    def _expect_ok(reply: Reply, command: str) -> None:
        if reply != "OK":
            raise CacheError(f"{command} answered {reply!r}")
