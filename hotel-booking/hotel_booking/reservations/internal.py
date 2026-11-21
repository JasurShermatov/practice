"""Reservations' internal code: where its rows are kept. Only Reservations, the wiring and tests import this.

The rows are Reservations' private data (P05): no other module reads them; they
ask Reservations through its contract or receive a ``Confirmation``.

Two stores keep the same ``ReservationStore`` promise:

- ``InMemoryReservationStore`` - a list; the demo, the race and the API tests use it.
- ``SqlReservationStore`` (P07) - the ``reservations`` table of ``db/postgres/init.sql`` over a
  DB-API 2 connection: ``sqlite3`` by default, ``psycopg`` for PostgreSQL on the student's Mac.
  The SQL text is identical for both; only the placeholder (``?`` / ``%s``) and the way a date is
  passed (ISO text / ``datetime.date``) differ, and both are decided in one place, ``_sql``/``_day``.

``BookingService`` did not change for P07: ``cancel`` still only changes the ``Reservation``
object; the SQL store remembers every reservation it hands out and writes the changed status in
``save_changes()`` at the end of the request (the unit of work in ``main.py``).
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from hotel_booking.reservations.domain import DateRange, Guest, Reservation, ReservationStatus
from hotel_booking.rooms import Room

# A DB-API 2 (PEP 249) connection: sqlite3.Connection or psycopg.Connection. The store only uses
# cursor(), commit() and rollback(); the two libraries share no base class, hence Any.
DbConnection = Any

# "A Confirmed reservation of this room shares at least one night with the stay" - the overlap
# rule of DateRange.overlaps (half-open: check_in < other.check_out AND other.check_in < check_out),
# written once in SQL. Parameters: room number, stay.check_out, stay.check_in.
BLOCKING = ("FROM reservations WHERE room = ? AND status = 'Confirmed' "
            "AND check_in < ? AND ? < check_out")

COUNT = "SELECT count(*) FROM reservations"
HAS_OVERLAP = f"SELECT EXISTS (SELECT 1 {BLOCKING})"
COUNT_CONFIRMED = f"SELECT count(*) {BLOCKING}"
INSERT = ("INSERT INTO reservations (id, guest_name, guest_email, room, check_in, check_out, status) "
          "VALUES (?, ?, ?, ?, ?, ?, ?)")
SELECT_BY_ID = ("SELECT id, guest_name, guest_email, room, check_in, check_out, status "
                "FROM reservations WHERE id = ?")
UPDATE_STATUS = "UPDATE reservations SET status = ? WHERE id = ?"


class InMemoryReservationStore:
    """Keeps every reservation ever saved in a list; keeps the ``ReservationStore`` promise by shape.

    History is kept: Cancelled reservations stay in the list.
    """

    def __init__(self) -> None:
        self._rows: list[Reservation] = []

    def count(self) -> int:
        return len(self._rows)

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return any(row.blocks(room, stay) for row in self._rows)

    def save(self, reservation: Reservation) -> None:
        # No check here: the caller checks first. That check-then-act gap is the race fixed in P09.
        self._rows.append(reservation)

    def find(self, reservation_id: str) -> Reservation | None:
        return next((row for row in self._rows if row.id == reservation_id), None)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return sum(1 for row in self._rows if row.blocks(room, stay))


class SqlReservationStore:
    """Keeps reservations in the ``reservations`` table; keeps the ``ReservationStore`` promise by shape.

    One store per request (a unit of work): it remembers each reservation it hands out or saves
    (an identity map, so ``find`` twice gives the same object), and ``save_changes`` writes the
    statuses that changed and commits. ``save`` INSERTs at once, so the primary key refuses a
    second ``R101`` inside the request that tries it (two app instances that both counted 0).
    Before an overlap question it first writes pending status changes (autoflush, not yet
    committed), so a cancel earlier in the same unit of work frees the room for the next
    question - exactly what the list store answers.

    Every value reaches the database as a bound parameter, never by string formatting.
    """

    def __init__(self, connection: DbConnection, rooms: Iterable[Room]) -> None:
        self._connection = connection
        self._rooms = {room.number: room for room in rooms}
        self._sqlite = isinstance(connection, sqlite3.Connection)
        # reservation id -> (the object handed out, its status as the database has it)
        self._loaded: dict[str, tuple[Reservation, ReservationStatus]] = {}

    # --- the ReservationStore promise -------------------------------------------------------

    def count(self) -> int:
        return int(self._scalar(COUNT))

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        self._flush()
        return bool(self._scalar(HAS_OVERLAP, *self._blocking(room, stay)))

    def save(self, reservation: Reservation) -> None:
        self._rows(INSERT, (
            reservation.id, reservation.guest.name, reservation.guest.email, reservation.room.number,
            self._day(reservation.stay.check_in), self._day(reservation.stay.check_out),
            reservation.status.value,
        ))
        self._loaded[reservation.id] = (reservation, reservation.status)

    def find(self, reservation_id: str) -> Reservation | None:
        if reservation_id in self._loaded:
            return self._loaded[reservation_id][0]
        rows = self._rows(SELECT_BY_ID, (reservation_id,))
        if not rows:
            return None
        reservation = self._to_reservation(rows[0])
        self._loaded[reservation.id] = (reservation, reservation.status)
        return reservation

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        self._flush()
        return int(self._scalar(COUNT_CONFIRMED, *self._blocking(room, stay)))

    # --- the end of the request --------------------------------------------------------------

    def save_changes(self) -> int:
        """Write the status of every handed-out reservation that changed, then commit.

        Returns how many rows this call updated (0 for a search or a refused booking). The caller
        rolls back instead when the request failed.
        """
        written = self._flush()
        self._connection.commit()
        return written

    # --- helpers -----------------------------------------------------------------------------

    def _flush(self) -> int:
        """UPDATE the rows whose reservation changed status since it was loaded (no commit)."""
        changed = [reservation for reservation, stored in self._loaded.values() if reservation.status is not stored]
        for reservation in changed:
            self._rows(UPDATE_STATUS, (reservation.status.value, reservation.id))
            self._loaded[reservation.id] = (reservation, reservation.status)
        return len(changed)

    def _blocking(self, room: Room, stay: DateRange) -> tuple[object, ...]:
        return room.number, self._day(stay.check_out), self._day(stay.check_in)

    def _day(self, day: date) -> object:
        """sqlite3 stores ISO text (its default date adapter is deprecated); psycopg takes a date."""
        return day.isoformat() if self._sqlite else day

    def _sql(self, text: str) -> str:
        """sqlite3 uses the ``?`` placeholder (paramstyle qmark), psycopg ``%s`` (format)."""
        return text if self._sqlite else text.replace("?", "%s")

    def _rows(self, text: str, params: Sequence[object] = ()) -> list[tuple[Any, ...]]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(self._sql(text), tuple(params))
            return [tuple(row) for row in cursor.fetchall()] if cursor.description else []
        finally:
            cursor.close()

    def _scalar(self, text: str, *params: object) -> Any:
        return self._rows(text, params)[0][0]

    def _to_reservation(self, row: tuple[Any, ...]) -> Reservation:
        reservation_id, guest_name, guest_email, room_number, check_in, check_out, status = row
        room = self._rooms.get(room_number)
        if room is None:
            raise LookupError(f"reservation {reservation_id} names room {room_number}, which the catalog does not sell")
        reservation = Reservation(reservation_id, Guest(guest_name, guest_email), room,
                                  DateRange(as_date(check_in), as_date(check_out)))
        if ReservationStatus(status) is ReservationStatus.CANCELLED:
            reservation.cancel()  # the only way to reach Cancelled: the entity keeps its rule
        return reservation


def as_date(value: object) -> date:
    """A date column as ``date``: psycopg returns one already, sqlite3 returns the ISO text."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"not a date column value: {value!r}")
