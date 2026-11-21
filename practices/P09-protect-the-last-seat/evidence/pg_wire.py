"""A minimal PostgreSQL client on the standard library - evidence tooling only, NOT part of the app.

Why it exists: the build container has a real PostgreSQL 16 server but no Python driver (psycopg
cannot be installed: no PyPI). To run the *real* app code - ``main.build_api`` with the unchanged
``SqlReservationStore`` - against PostgreSQL, this file speaks just enough of PostgreSQL's
frontend/backend protocol (version 3) to look like a DB-API 2 connection in psycopg's style:

- ``connect(host, port, user, database)`` with *trust* authentication only (the throw-away test
  cluster allows 127.0.0.1 without a password; the Docker database on the Mac uses a password and
  psycopg - this file is never used there);
- ``connection.cursor().execute(sql, params)`` with psycopg's ``%s`` placeholders, sent as the
  extended query protocol (Parse/Bind/Describe/Execute/Sync) with text parameters - values are
  bound, never pasted into the SQL;
- a transaction starts implicitly at the first statement (BEGIN), like psycopg's default;
  ``commit()`` / ``rollback()`` end it;
- errors are raised as ``PgError`` with ``sqlstate`` and ``diag.constraint_name`` - the two
  attributes of psycopg 3's errors the store reads to recognise 23P01 on reservations_no_overlap;
- result columns are converted by type OID: bool, integers, date; everything else stays text.

What it does not do: SSL, passwords, COPY, binary formats, notices, cancellation, pooling.
"""
from __future__ import annotations

import socket
import struct
from dataclasses import dataclass
from datetime import date
from typing import Any

BOOL, INT8, INT2, INT4, DATE = 16, 20, 21, 23, 1082


@dataclass(frozen=True)
class Diagnostics:
    constraint_name: str | None
    detail: str | None


class PgError(Exception):
    """An ErrorResponse from the server, shaped like psycopg 3's errors (sqlstate, diag)."""

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__(fields.get("M", "unknown error"))
        self.sqlstate = fields.get("C")
        self.diag = Diagnostics(fields.get("n"), fields.get("D"))


def _to_python(type_oid: int, raw: bytes | None) -> Any:
    if raw is None:
        return None
    text = raw.decode()
    if type_oid == BOOL:
        return text == "t"
    if type_oid in (INT2, INT4, INT8):
        return int(text)
    if type_oid == DATE:
        return date.fromisoformat(text)
    return text


def _to_text(value: object) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return b"true" if value else b"false"
    if isinstance(value, date):
        return value.isoformat().encode()
    return str(value).encode()


def _placeholders(sql: str) -> str:
    """psycopg's %s -> PostgreSQL's $1, $2 ... (the store's SQL has no other % in it)."""
    parts = sql.split("%s")
    return "".join(part + (f"${index}" if index < len(parts) else "") for index, part in enumerate(parts, start=1))


class Connection:
    def __init__(self, host: str, port: int, user: str, database: str) -> None:
        self._socket = socket.create_connection((host, port), timeout=60)
        self._buffer = b""
        self.in_transaction = False
        body = struct.pack("!i", 196608)  # protocol 3.0
        for key, value in (("user", user), ("database", database), ("application_name", "p09-evidence")):
            body += key.encode() + b"\0" + value.encode() + b"\0"
        body += b"\0"
        self._socket.sendall(struct.pack("!i", len(body) + 4) + body)
        error: PgError | None = None
        while True:
            kind, payload = self._read()
            if kind == b"R" and struct.unpack("!i", payload[:4])[0] != 0:
                raise PgError({"M": "only trust authentication is supported by this evidence client"})
            if kind == b"E":
                error = PgError(self._fields(payload))
            if kind == b"Z":
                break
        if error is not None:
            raise error

    # --- DB-API surface -------------------------------------------------------------------

    def cursor(self) -> Cursor:
        return Cursor(self)

    def commit(self) -> None:
        if self.in_transaction:
            self._simple("COMMIT")
            self.in_transaction = False

    def rollback(self) -> None:
        if self.in_transaction:
            self._simple("ROLLBACK")
            self.in_transaction = False

    def close(self) -> None:
        try:
            self._socket.sendall(b"X" + struct.pack("!i", 4))
        finally:
            self._socket.close()

    # --- protocol ---------------------------------------------------------------------------

    def run(self, sql: str, params: tuple[object, ...]) -> tuple[list[str] | None, list[tuple[Any, ...]]]:
        """One statement with the extended protocol; returns (column names or None, rows)."""
        if not self.in_transaction:
            self._simple("BEGIN")
            self.in_transaction = True
        query = _placeholders(sql).encode() + b"\0"
        parse = b"\0" + query + struct.pack("!h", 0)
        bind = b"\0\0" + struct.pack("!hh", 0, len(params))
        for value in params:
            raw = _to_text(value)
            bind += struct.pack("!i", -1) if raw is None else struct.pack("!i", len(raw)) + raw
        bind += struct.pack("!h", 0)
        message = (self._message(b"P", parse) + self._message(b"B", bind) + self._message(b"D", b"P\0")
                   + self._message(b"E", b"\0" + struct.pack("!i", 0)) + self._message(b"S", b""))
        self._socket.sendall(message)
        names: list[str] | None = None
        types: list[int] = []
        rows: list[tuple[Any, ...]] = []
        error: PgError | None = None
        while True:
            kind, payload = self._read()
            if kind == b"T":
                names, types = self._row_description(payload)
            elif kind == b"D":
                rows.append(self._data_row(payload, types))
            elif kind == b"E":
                error = PgError(self._fields(payload))
            elif kind == b"Z":
                break
        if error is not None:
            raise error
        return names, rows

    def _simple(self, sql: str) -> None:
        self._socket.sendall(self._message(b"Q", sql.encode() + b"\0"))
        error: PgError | None = None
        while True:
            kind, payload = self._read()
            if kind == b"E":
                error = PgError(self._fields(payload))
            if kind == b"Z":
                break
        if error is not None:
            raise error

    @staticmethod
    def _message(kind: bytes, payload: bytes) -> bytes:
        return kind + struct.pack("!i", len(payload) + 4) + payload

    def _read_exactly(self, size: int) -> bytes:
        while len(self._buffer) < size:
            chunk = self._socket.recv(65536)
            if not chunk:
                raise PgError({"C": "08006", "M": "the server closed the connection"})
            self._buffer += chunk
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data

    def _read(self) -> tuple[bytes, bytes]:
        header = self._read_exactly(5)
        kind, length = header[:1], struct.unpack("!i", header[1:])[0]
        return kind, self._read_exactly(length - 4)

    @staticmethod
    def _fields(payload: bytes) -> dict[str, str]:
        fields: dict[str, str] = {}
        for part in payload.split(b"\0"):
            if part:
                fields[chr(part[0])] = part[1:].decode()
        return fields

    @staticmethod
    def _row_description(payload: bytes) -> tuple[list[str], list[int]]:
        count = struct.unpack("!h", payload[:2])[0]
        names, types, offset = [], [], 2
        for _ in range(count):
            end = payload.index(b"\0", offset)
            names.append(payload[offset:end].decode())
            table_oid, column, type_oid, size, modifier, fmt = struct.unpack("!ihihih", payload[end + 1:end + 19])
            types.append(type_oid)
            offset = end + 19
        return names, types

    def _data_row(self, payload: bytes, types: list[int]) -> tuple[Any, ...]:
        count = struct.unpack("!h", payload[:2])[0]
        values, offset = [], 2
        for index in range(count):
            length = struct.unpack("!i", payload[offset:offset + 4])[0]
            offset += 4
            raw = None if length == -1 else payload[offset:offset + length]
            offset += max(length, 0)
            values.append(_to_python(types[index], raw))
        return tuple(values)


class Cursor:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self.description: tuple[tuple[str], ...] | None = None
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        names, self._rows = self._connection.run(sql, tuple(params))
        self.description = None if names is None else tuple((name,) for name in names)

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self._rows = self._rows, []
        return rows

    def close(self) -> None:
        self._rows = []


def connect(host: str = "127.0.0.1", port: int = 5432, user: str = "hotel", database: str = "hotel") -> Connection:
    return Connection(host, port, user, database)
