"""Where reservations are kept (P03: an in-memory list).

Version 1 keeps everything in memory, so restarting the program clears it.
P04 puts this class behind an interface; P07 replaces it with a database.
"""
from __future__ import annotations

from .domain import DateRange, Reservation, Room


class ReservationStore:
    """Keeps every reservation ever saved, Confirmed or Cancelled (history is kept)."""

    def __init__(self) -> None:
        self._rows: list[Reservation] = []

    def count(self) -> int:
        """Number of saved reservations, including Cancelled ones (used to number new ids)."""
        return len(self._rows)

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        """True when any saved reservation blocks ``room`` for ``stay`` (R3)."""
        return any(row.blocks(room, stay) for row in self._rows)

    def save(self, reservation: Reservation) -> None:
        """Append ``reservation``. No check here: the caller checks first (see P09 for why that is a problem)."""
        self._rows.append(reservation)

    def find(self, reservation_id: str) -> Reservation | None:
        """The reservation with this id, or ``None`` (R5)."""
        return next((row for row in self._rows if row.id == reservation_id), None)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        """How many Confirmed reservations block ``room`` for ``stay``; R3 requires at most 1."""
        return sum(1 for row in self._rows if row.blocks(room, stay))
