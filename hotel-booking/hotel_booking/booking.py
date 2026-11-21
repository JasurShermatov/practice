"""The booking workflow: one method per use case (P03).

``BookingService.reserve`` is the "Sequence - book" diagram in code and its
two ``if`` statements are the two decisions of the "Activity - book" diagram:

1. check-out after check-in?            -> otherwise InvalidDates, save nothing
2. a Confirmed booking shares a night?  -> otherwise Unavailable, save nothing
3. save the reservation as Confirmed, then send the confirmation, then answer.
"""
from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .domain import DateRange, Guest, Reservation, Room
from .notifications import EmailSender
from .stores import ReservationStore

FIRST_RESERVATION_NUMBER = 101


class BookingOutcome(Enum):
    """The three answers a Reserve request can get."""

    ACCEPTED = "Accepted"
    UNAVAILABLE = "Unavailable"
    INVALID_DATES = "InvalidDates"


@dataclass(frozen=True)
class BookingResult:
    """What the guest sees: the outcome, plus the reservation id when Accepted."""

    outcome: BookingOutcome
    reservation_id: str | None = None

    def __str__(self) -> str:
        if self.reservation_id is None:
            return self.outcome.value
        return f"{self.outcome.value} {self.reservation_id}"


class BookingService:
    """Runs every request in the right order. It is handed its store and sender; it owns neither."""

    def __init__(
        self,
        rooms: Iterable[Room],
        store: ReservationStore,
        email: EmailSender,
        slow_step_seconds: float = 0.0,
    ) -> None:
        self._rooms = list(rooms)
        self._store = store
        self._email = email
        # Demo-only knob: widens the gap between "check" and "save" so the
        # race condition of Step 8 becomes visible. 0 in normal use.
        self._slow_step_seconds = slow_step_seconds

    def find_free_rooms(self, stay: DateRange) -> list[Room]:
        """R1 - rooms of the hotel with no Confirmed booking sharing a night with ``stay``."""
        return [room for room in self._rooms if not self._store.has_overlap(room, stay)]

    def reserve(self, guest: Guest, room: Room, stay: DateRange) -> BookingResult:
        """R2/R3 - book ``room`` for ``guest`` if the dates are valid and the room is free."""
        if not stay.is_valid():
            return BookingResult(BookingOutcome.INVALID_DATES)
        if self._store.has_overlap(room, stay):  # check ...
            return BookingResult(BookingOutcome.UNAVAILABLE)

        if self._slow_step_seconds:
            time.sleep(self._slow_step_seconds)  # ... the gap (demo only) ...

        reservation = Reservation(self._next_id(), guest, room, stay)
        self._store.save(reservation)  # ... then act. Not atomic: see design-notes "The race".
        self._email.send_confirmation(reservation)  # only after the save
        return BookingResult(BookingOutcome.ACCEPTED, reservation.id)

    def cancel(self, reservation_id: str) -> bool:
        """R4 - cancel a booking; it stays in the store as Cancelled and stops blocking the room."""
        reservation = self._store.find(reservation_id)
        return reservation is not None and reservation.cancel()

    def _next_id(self) -> str:
        # Ids are never reused because reservations are never deleted.
        return f"R{FIRST_RESERVATION_NUMBER + self._store.count()}"
