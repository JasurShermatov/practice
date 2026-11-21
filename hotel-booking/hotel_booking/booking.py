"""The booking workflow: one method per use case (P03; P04: depends only on two promises).

``BookingService.reserve`` is the "Sequence - book" diagram in code and its
two ``if`` statements are the two decisions of the "Activity - book" diagram:

1. check-out after check-in?            -> otherwise InvalidDates, save nothing
2. a Confirmed booking shares a night?  -> otherwise Unavailable, save nothing
3. save the reservation as Confirmed, then send the confirmation, then answer.
   If sending fails, the booking stays saved and Accepted and the failure is
   reported in the result (R6, P04 Step 7).

Since P04 ``BookingService`` names no concrete helper: it asks for a
``ReservationStore`` and a ``NotificationSender`` (both ``typing.Protocol``)
and ``main.py`` decides which real classes to pass in (dependency inversion).
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .domain import DateRange, Guest, Reservation, Room
from .notifications import NotificationSender
from .stores import ReservationStore

FIRST_RESERVATION_NUMBER = 101

logger = logging.getLogger(__name__)


class BookingOutcome(Enum):
    """The three answers a Reserve request can get."""

    ACCEPTED = "Accepted"
    UNAVAILABLE = "Unavailable"
    INVALID_DATES = "InvalidDates"


@dataclass(frozen=True)
class BookingResult:
    """What the guest sees: the outcome, plus the reservation id when Accepted.

    ``notification_failed`` is True when the booking was saved but its
    confirmation could not be sent (R6). It does not change the printed text.
    """

    outcome: BookingOutcome
    reservation_id: str | None = None
    notification_failed: bool = False

    def __str__(self) -> str:
        if self.reservation_id is None:
            return self.outcome.value
        return f"{self.outcome.value} {self.reservation_id}"


class BookingService:
    """Runs every request in the right order. It is handed its store and sender; it owns neither.

    It knows them only through their promises, so any store or sender with the
    right methods fits: the in-memory list or (P07) a database; email, SMS or a
    fake in the tests.
    """

    def __init__(
        self,
        rooms: Iterable[Room],
        store: ReservationStore,
        notifications: NotificationSender,
        slow_step_seconds: float = 0.0,
    ) -> None:
        self._rooms = list(rooms)
        self._store = store
        self._notifications = notifications
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
        delivered = self._try_to_confirm(reservation)  # only after the save
        return BookingResult(BookingOutcome.ACCEPTED, reservation.id, notification_failed=not delivered)

    def cancel(self, reservation_id: str) -> bool:
        """R4 - cancel a booking; it stays in the store as Cancelled and stops blocking the room."""
        reservation = self._store.find(reservation_id)
        return reservation is not None and reservation.cancel()

    def _next_id(self) -> str:
        # Ids are never reused because reservations are never deleted.
        return f"R{FIRST_RESERVATION_NUMBER + self._store.count()}"

    def _try_to_confirm(self, reservation: Reservation) -> bool:
        """Ask the sender to confirm; True if it did. R6: a failure must not undo or hide the booking.

        Any ``Exception`` from the sender is caught on purpose: whatever the
        channel (SMTP error, SMS gateway timeout, ...), the reservation is already
        saved and Confirmed, so the guest's answer stays Accepted. The failure is
        logged and reported through ``BookingResult.notification_failed``.
        ``BaseException`` (e.g. KeyboardInterrupt) is not caught.
        """
        try:
            self._notifications.send_confirmation(reservation)
        except Exception:
            logger.warning("Confirmation for %s could not be sent; the booking stays saved.",
                           reservation.id, exc_info=True)
            return False
        return True
