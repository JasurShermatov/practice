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

P09 - both stores now keep the whole promise themselves (docs/adr-003-booking-concurrency.md):

- ``save`` refuses an overlapping Confirmed reservation with ``OverlapRejected``. The list store
  checks and appends under one lock. The SQL store lets the *database* refuse the INSERT and only
  translates that one refusal: in PostgreSQL the exclusion constraint ``reservations_no_overlap``
  (SQLSTATE 23P01), in SQLite the triggers of the same name (``db/sqlite/init.sql``). Every other
  database error - a duplicate id, a lost connection - is re-raised untouched: it is a fault,
  not a full room, and answering "taken" would hide it.
- ``next_reservation_id`` hands out ids no other request gets: PostgreSQL ``nextval`` on the
  sequence ``reservation_ids``; SQLite an UPDATE ... RETURNING on its one-row table of the same
  name (SQLite has no sequences; the UPDATE holds SQLite's single write lock until COMMIT); the
  list store a counter under its lock.
- PostgreSQL aborts the whole transaction when one statement fails, so the INSERT runs inside a
  SAVEPOINT and a refusal rolls back only that statement; the request can still COMMIT (and the
  unit of work does). SQLite backs out only the failed statement by itself - no savepoint needed.
- Found by running the race for real (P09 evidence): when two conflicting INSERTs reach the
  exclusion constraint at the same instant, each can find the other's undecided row and wait for
  it - PostgreSQL then aborts one with *deadlock detected* (40P01) instead of 23P01. The store rolls
  back to the savepoint and tries the INSERT again (at most ``INSERT_ATTEMPTS`` times): by then the
  other booking has committed (the retry gets 23P01 -> OverlapRejected -> 409) or rolled back (the
  retry succeeds). Before this retry those requests were answered 500.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from hotel_booking.reservations.booking import FIRST_RESERVATION_NUMBER, OverlapRejected
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

# P09 Step 1: the next reservation number, from the database (never from counting the rows).
NEXT_ID_POSTGRES = "SELECT nextval('reservation_ids')"  # a sequence: never the same number twice
NEXT_ID_SQLITE = "UPDATE reservation_ids SET last_value = last_value + 1 RETURNING last_value"  # one-row table

# P09 Step 7: PostgreSQL rolls the whole transaction back after a failed statement; a savepoint
# around the INSERT limits that to the INSERT, so the request can still commit.
SAVEPOINT = "SAVEPOINT reservation_insert"
RELEASE_SAVEPOINT = "RELEASE SAVEPOINT reservation_insert"
ROLLBACK_TO_SAVEPOINT = "ROLLBACK TO SAVEPOINT reservation_insert"

# The name of the rule in both schema files. The store recognises this one refusal and turns it
# into OverlapRejected; any other database error is a real fault and is re-raised.
NO_OVERLAP_CONSTRAINT = "reservations_no_overlap"
EXCLUSION_VIOLATION = "23P01"                         # PostgreSQL SQLSTATE exclusion_violation
DEADLOCK_DETECTED = "40P01"                           # two conflicting INSERTs waited for each other
INSERT_ATTEMPTS = 3                                   # a retry loop always needs a limit
SQLITE_TRIGGER_REFUSAL = "SQLITE_CONSTRAINT_TRIGGER"  # RAISE(ABORT, ...) inside a trigger

REFUSED = "{room} already has a Confirmed reservation for at least one of these nights."
ID_NUMBER = re.compile(r"R([0-9]+)")


def is_overlap_refusal(error: BaseException) -> bool:
    """True only for the database refusing a double booking - never for any other error.

    SQLite: the trigger ``RAISE(ABORT, 'reservations_no_overlap: ...')`` arrives as an
    ``IntegrityError`` whose error name is SQLITE_CONSTRAINT_TRIGGER. PostgreSQL (psycopg): the
    error's ``sqlstate`` is 23P01 and ``diag.constraint_name`` is the constraint's name. Both the
    code and the name must match: a duplicate id is also an integrity error (SQLITE_CONSTRAINT_PRIMARYKEY,
    23505), and calling that a full room would hide a real bug.
    """
    if isinstance(error, sqlite3.IntegrityError):
        return (getattr(error, "sqlite_errorname", None) == SQLITE_TRIGGER_REFUSAL
                and str(error).startswith(NO_OVERLAP_CONSTRAINT))
    diagnostics = getattr(error, "diag", None)
    return (getattr(error, "sqlstate", None) == EXCLUSION_VIOLATION
            and getattr(diagnostics, "constraint_name", None) == NO_OVERLAP_CONSTRAINT)


class InMemoryReservationStore:
    """Keeps every reservation ever saved in a list; keeps the ``ReservationStore`` promise by shape.

    History is kept: Cancelled reservations stay in the list. P09: ``save`` checks for an overlap
    and appends while holding one lock, and ids come from a counter under the same lock. This
    list is the whole database here, so the lock is this store's exclusion constraint and its
    sequence. It works for the threads of *this process only*: a second copy of the app has a
    second list and a second lock (docs/interleaving.md, Step 4) - which is why the SQL store
    leaves the rule to the database instead.
    """

    def __init__(self) -> None:
        self._rows: list[Reservation] = []
        self._last_number = FIRST_RESERVATION_NUMBER - 1
        self._lock = threading.Lock()

    def count(self) -> int:
        return len(self._rows)

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return self._blocked(room, stay)

    def next_reservation_id(self) -> str:
        with self._lock:
            self._last_number += 1
            return f"R{self._last_number}"

    def save(self, reservation: Reservation) -> None:
        with self._lock:  # check and append with no other thread in between
            if any(row.id == reservation.id for row in self._rows):
                raise ValueError(f"reservation id {reservation.id} is already used")  # the primary key's job
            if self._blocked(reservation.room, reservation.stay):
                raise OverlapRejected(REFUSED.format(room=reservation.room.number))
            self._rows.append(reservation)
            # An id saved from outside next_reservation_id (a test, an import) is never handed out again.
            if (number := ID_NUMBER.fullmatch(reservation.id)) is not None:
                self._last_number = max(self._last_number, int(number.group(1)))

    def find(self, reservation_id: str) -> Reservation | None:
        return next((row for row in self._rows if row.id == reservation_id), None)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return sum(1 for row in self._rows if row.blocks(room, stay))

    def _blocked(self, room: Room, stay: DateRange) -> bool:
        """The overlap rule itself; ``save`` asks it directly, inside its lock."""
        return any(row.blocks(room, stay) for row in self._rows)


class SqlReservationStore:
    """Keeps reservations in the ``reservations`` table; keeps the ``ReservationStore`` promise by shape.

    One store per request (a unit of work): it remembers each reservation it hands out or saves
    (an identity map, so ``find`` twice gives the same object), and ``save_changes`` writes the
    statuses that changed and commits. ``save`` INSERTs at once, so the database answers inside
    the request: the no-overlap rule (P09) and the primary key are checked as the row goes in.
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

    def next_reservation_id(self) -> str:
        number = self._scalar(NEXT_ID_SQLITE if self._sqlite else NEXT_ID_POSTGRES)
        return f"R{int(number)}"

    def save(self, reservation: Reservation) -> None:
        row = (
            reservation.id, reservation.guest.name, reservation.guest.email, reservation.room.number,
            self._day(reservation.stay.check_in), self._day(reservation.stay.check_out),
            reservation.status.value,
        )
        try:
            self._insert(row)
        except Exception as error:  # sqlite3 and psycopg share no base class
            if is_overlap_refusal(error):
                raise OverlapRejected(REFUSED.format(room=reservation.room.number)) from error
            raise  # a duplicate id, a lost connection ...: a real fault, not a double booking
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

    def _insert(self, row: tuple[object, ...]) -> None:
        """INSERT one reservation; on PostgreSQL inside a savepoint (see the module docstring)."""
        if self._sqlite:
            self._rows(INSERT, row)  # a refused statement is backed out alone; the transaction lives on
            return
        for attempt in range(1, INSERT_ATTEMPTS + 1):
            self._rows(SAVEPOINT)
            try:
                self._rows(INSERT, row)
            except Exception as error:
                self._rows(ROLLBACK_TO_SAVEPOINT)  # forget the failed INSERT, keep the transaction
                if getattr(error, "sqlstate", None) == DEADLOCK_DETECTED and attempt < INSERT_ATTEMPTS:
                    continue  # the other booking has decided by now: try again and get its answer
                raise
            self._rows(RELEASE_SAVEPOINT)
            return

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
