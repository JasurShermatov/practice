"""What the searches cost (P08 Step 1): the counters of GET /stats and the counting store.

Both live at the HTTP edge, next to ``api.py``, not inside a module: they measure the app, they
are not part of the hotel's rules. ``BookingService`` does not know they exist - the wiring puts
the counting store *around* the real store (the decorator idea from P04: it keeps the same
``ReservationStore`` promise), so every question the booking service asks the database is
counted without changing a line of Reservations.

The counters start at 0 when the app starts and only grow. Requests run on several threads at
once (Starlette's thread pool), so every ``+= 1`` happens under a lock.
"""
from __future__ import annotations

import threading
from typing import Literal, get_args

from hotel_booking.reservations import DateRange, Reservation, ReservationStore
from hotel_booking.rooms import Room

Counter = Literal["searches", "databaseQueries", "cacheHits", "cacheMisses", "cacheErrors"]
COUNTERS: tuple[Counter, ...] = get_args(Counter)


class Stats:
    """The counters of GET /stats, named as on the wire (camelCase).

    - ``searches``: searches that passed the request checks and reached the search;
    - ``databaseQueries``: questions the reservation store sent to the database;
    - ``cacheHits``: searches answered from a copy in the cache;
    - ``cacheMisses``: searches that found no copy, asked the database and stored a copy;
    - ``cacheErrors``: cache commands that failed (the request went on without the cache).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[Counter, int] = dict.fromkeys(COUNTERS, 0)

    def add(self, counter: Counter) -> None:
        with self._lock:
            self._counts[counter] += 1

    def snapshot(self) -> dict[Counter, int]:
        """A consistent copy of all counters (read under the same lock as the writes)."""
        with self._lock:
            return dict(self._counts)


class CountingReservationStore:
    """Passes every call on to the real store and counts it: each call is one database question.

    A ``SqlReservationStore`` answers each promised call with one SQL statement (P07,
    ``test_a_search_asks_the_database_once_per_room``), so for a search this count is the number
    of queries. Not counted: the unit of work's final ``save_changes`` (not a promised call) and
    the autoflush UPDATE written before a question when a status change is pending.
    """

    def __init__(self, store: ReservationStore, stats: Stats) -> None:
        self._store = store
        self._stats = stats

    def count(self) -> int:
        self._stats.add("databaseQueries")
        return self._store.count()

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        self._stats.add("databaseQueries")
        return self._store.has_overlap(room, stay)

    def save(self, reservation: Reservation) -> None:
        self._stats.add("databaseQueries")
        self._store.save(reservation)

    def find(self, reservation_id: str) -> Reservation | None:
        self._stats.add("databaseQueries")
        return self._store.find(reservation_id)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        self._stats.add("databaseQueries")
        return self._store.count_confirmed(room, stay)
