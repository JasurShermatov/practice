"""The booking workflow, owned by Reservations (P03 rules, P04 seams, P06 module).

``BookingService.reserve`` is the "Sequence - book" diagram in code and its
two ``if`` statements are the two decisions of the "Activity - book" diagram:

1. check-out after check-in?            -> otherwise InvalidDates, save nothing
2. a Confirmed booking shares a night?  -> otherwise Unavailable, save nothing
3. save the reservation as Confirmed, then send the confirmation, then answer.
   If sending fails, the booking stays saved and Accepted and the failure is
   reported in the result (R6).

P09 - the last seat is protected where every writer must pass: in the store. Step 2 (the
pre-check) is kept, because it answers the ordinary case with a readable Unavailable, but it is
no longer what makes the rule true. Two requests can both pass it in the same moment (write
skew, docs/interleaving.md). So ``ReservationStore.save`` now *promises* to refuse a
reservation that would give the room two Confirmed reservations for one night, by raising
``OverlapRejected``; ``reserve`` turns that refusal into the same Unavailable. How a store keeps
the promise is its own business: a lock in the list store, a trigger in SQLite, the exclusion
constraint ``reservations_no_overlap`` in PostgreSQL (docs/adr-003-booking-concurrency.md).

The reservation id now comes from the store as well (``next_reservation_id``): counting the rows
and adding one is a second race - two requests that count before either saves both get R101.

``BookingService`` knows the other modules only by their public contracts:
``Room`` (Rooms) and ``NotificationSender`` / ``Confirmation`` (Notifications).
It never names an internal class of another module (architecture rule 1); the
wiring in ``main.py`` hands it the real store and sender.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from hotel_booking.notifications import Confirmation, NotificationSender
from hotel_booking.reservations.domain import DateRange, Guest, Reservation
from hotel_booking.rooms import Room

FIRST_RESERVATION_NUMBER = 101

logger = logging.getLogger(__name__)


class OverlapRejected(Exception):
    """A store refused to save a reservation that would double-book its room (P09).

    Part of the ``ReservationStore`` promise: ``save`` raises it instead of writing a second
    Confirmed reservation for the same room and night. ``BookingService.reserve`` turns it into
    Unavailable - the answer the pre-check gives - so a guest never sees a database error.
    Anything else a store raises (a duplicate id, a lost connection) is a real fault, not this.
    """


class ReservationStore(Protocol):
    """What BookingService needs from storage: Reservations' private rows. A list or a database."""

    def count(self) -> int:
        """Number of saved reservations, Cancelled ones included."""
        ...

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        """True when a saved reservation blocks ``room`` for ``stay`` (R3)."""
        ...

    def next_reservation_id(self) -> str:
        """A new reservation id (R101, R102 ...) that no other request is ever given (P09).

        The store owns this because only the store can promise it: counting the rows and adding
        one hands R101 to two requests that count before either has saved, and the second INSERT
        then fails on the primary key - the wrong error for the wrong reason. A number that was
        handed out and not used (the booking was refused) is not handed out again.
        """
        ...

    def save(self, reservation: Reservation) -> None:
        """Keep ``reservation``.

        Raises ``OverlapRejected`` - and keeps nothing - if a Confirmed reservation of the same
        room already covers one of its nights. The pre-check in ``reserve`` usually answers first;
        this promise is what keeps R3 true when two requests check at the same moment.
        """
        ...

    def find(self, reservation_id: str) -> Reservation | None:
        """The reservation with this id, or ``None`` (R5)."""
        ...

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        """How many Confirmed reservations block ``room`` for ``stay``; R3 requires at most 1."""
        ...


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
    """Owns the booking rule and runs every request in the right order.

    It is handed the rooms on sale, its store and a sender; it owns none of
    them. Same constructor as in P04, so the P04 tests did not change.
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
        # Experiment knob: widens the gap between "check" and "save" so a race can be aimed at
        # (the --race demo, HOTEL_SLOW_STEP for tools/race_http.py). 0 in normal use. Since P09 a
        # wide gap no longer breaks R3; it only makes the refused request easy to observe.
        self._slow_step_seconds = slow_step_seconds

    def find_free_rooms(self, stay: DateRange) -> list[Room]:
        """R1 - rooms on sale with no Confirmed booking sharing a night with ``stay``."""
        return [room for room in self._rooms if not self._store.has_overlap(room, stay)]

    def reserve(self, guest: Guest, room: Room, stay: DateRange) -> BookingResult:
        """R2/R3 - book ``room`` for ``guest`` if the dates are valid and the room is free."""
        if not stay.is_valid():
            return BookingResult(BookingOutcome.INVALID_DATES)
        if self._store.has_overlap(room, stay):  # the pre-check: the ordinary, readable refusal
            return BookingResult(BookingOutcome.UNAVAILABLE)

        if self._slow_step_seconds:
            time.sleep(self._slow_step_seconds)  # the gap, widened on purpose (experiments only)

        reservation = Reservation(self._store.next_reservation_id(), guest, room, stay)
        try:
            self._store.save(reservation)  # the store refuses a double booking itself (P09)
        except OverlapRejected:
            # Another request saved an overlapping reservation after our check and before our
            # save. The check was true when it ran; it had stopped being true. Same answer.
            logger.info("%s lost the race for %s %s; answered Unavailable.", reservation.id, room.number, stay)
            return BookingResult(BookingOutcome.UNAVAILABLE)
        delivered = self._try_to_confirm(reservation)  # only after the save
        return BookingResult(BookingOutcome.ACCEPTED, reservation.id, notification_failed=not delivered)

    def cancel(self, reservation_id: str) -> bool:
        """R4 - cancel a booking; it stays in the store as Cancelled and stops blocking the room."""
        reservation = self._store.find(reservation_id)
        return reservation is not None and reservation.cancel()

    def _try_to_confirm(self, reservation: Reservation) -> bool:
        """Announce ReservationConfirmed to Notifications; True if the sender took it.

        The translation to Notifications' own ``Confirmation`` happens here, on
        Reservations' side of the border, so Notifications never needs the
        ``Reservation`` class. R6: any ``Exception`` from the sender is caught
        on purpose - the reservation is already saved and Confirmed, so the
        answer stays Accepted; the failure is logged and reported through
        ``BookingResult.notification_failed``. ``BaseException`` is not caught.
        """
        confirmation = Confirmation(
            reservation_id=reservation.id,
            guest_email=reservation.guest.email,
            room_number=reservation.room.number,
            check_in=reservation.stay.check_in,
            check_out=reservation.stay.check_out,
        )
        try:
            self._notifications.send_confirmation(confirmation)
        except Exception:
            logger.warning("Confirmation for %s could not be sent; the booking stays saved.",
                           reservation.id, exc_info=True)
            return False
        return True
