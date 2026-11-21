"""Where reservations are kept (P04: a promise and the class that keeps it).

``ReservationStore`` is the *promise* (a ``typing.Protocol``): the five
questions and commands BookingService needs from storage. ``BookingService``
depends only on it; ``InMemoryReservationStore`` (the P03 list, renamed) keeps
it today, and P07 adds a database store with the same five methods.

Version 2 still keeps everything in memory, so restarting the program clears it.
"""
from __future__ import annotations

from typing import Protocol

from .domain import DateRange, Reservation, Room


class ReservationStore(Protocol):
    """What BookingService needs from storage. Today a list in memory; from P07 a database."""

    def count(self) -> int:
        """Number of saved reservations, Cancelled ones included (used to number new ids)."""
        ...

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        """True when a saved reservation blocks ``room`` for ``stay`` (R3)."""
        ...

    def save(self, reservation: Reservation) -> None:
        """Keep ``reservation``."""
        ...

    def find(self, reservation_id: str) -> Reservation | None:
        """The reservation with this id, or ``None`` (R5)."""
        ...

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        """How many Confirmed reservations block ``room`` for ``stay``; R3 requires at most 1."""
        ...


class InMemoryReservationStore:
    """Keeps every reservation ever saved in a list (was ``ReservationStore`` in P03).

    Keeps the ``ReservationStore`` promise by shape: it has all five methods.
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
