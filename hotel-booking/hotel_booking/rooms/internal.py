"""Rooms' internal code: how the catalog keeps its promise. Only Rooms, the wiring and tests import this.

P07 adds ``SqlRoomCatalog``, which reads the ``rooms`` table of ``db/postgres/init.sql``. It takes
any DB-API 2 connection: ``sqlite3`` (the default wiring and the tests) or ``psycopg`` (PostgreSQL
from ``docker-compose.yml`` on the student's Mac). The SQL is the same for both.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from hotel_booking.rooms.catalog import Room

# A DB-API 2 (PEP 249) connection: sqlite3.Connection or psycopg.Connection. Only cursor() is
# used here; the two libraries share no base class, hence Any.
DbConnection = Any

SELECT_ROOMS = "SELECT number, type FROM rooms ORDER BY number"


class InMemoryRoomCatalog:
    """Keeps the hotel's rooms in a list; keeps the ``RoomCatalog`` promise by shape."""

    def __init__(self, rooms: Iterable[Room]) -> None:
        self._rooms = list(rooms)

    def all(self) -> list[Room]:
        # A copy: a caller that edits the list it got must not change the catalog.
        return list(self._rooms)


class SqlRoomCatalog:
    """Reads the rooms table; keeps the ``RoomCatalog`` promise by shape.

    The wiring asks it once, when the app starts (a new room = one INSERT and a restart). Rooms
    come in text order of their number (R10 before R7), the order the API contract promises.
    """

    def __init__(self, connection: DbConnection) -> None:
        self._connection = connection

    def all(self) -> list[Room]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(SELECT_ROOMS)
            return [Room(str(number), str(kind)) for number, kind in cursor.fetchall()]
        finally:
            cursor.close()
