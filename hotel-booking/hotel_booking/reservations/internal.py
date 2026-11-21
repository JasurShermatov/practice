"""Reservations' internal code: where its rows are kept. Only Reservations, the wiring and tests import this.

The rows are Reservations' private data (P05): no other module reads them; they
ask Reservations through its contract or receive a ``Confirmation``. P07 adds
the SQLite/PostgreSQL store next to this one, with the same five methods.
"""
from __future__ import annotations

from hotel_booking.reservations.domain import DateRange, Reservation
from hotel_booking.rooms import Room


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
