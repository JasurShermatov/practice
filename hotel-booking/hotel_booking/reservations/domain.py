"""The words of the Reservations context (P03 classes; moved here unchanged in P06).

Data classes only: they keep the facts of a booking and the rules that need
nothing but those facts (rule cards 1-3). Nothing here knows about storage or
messages; the only other module named is the Rooms contract (``Room``).

- ``DateRange`` (the Stay) is a *value*: equal when its dates are equal, never changes.
- ``Guest`` is plain reference data; ``Room`` comes from the Rooms module.
- ``Reservation`` is an *entity*: recognised by its id, its status changes
  (Confirmed -> Cancelled) only through ``cancel()``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from hotel_booking.rooms import Room


@dataclass(frozen=True)
class DateRange:
    """A stay as a half-open range of nights: ``[check_in, check_out)``.

    The check-in day is a night of the stay; the check-out day is not, so a
    new guest may check in on the day the previous guest checks out.
    """

    check_in: date
    check_out: date

    def is_valid(self) -> bool:
        """A stay must contain at least one night (R3: check-out after check-in)."""
        return self.check_out > self.check_in

    def overlaps(self, other: DateRange) -> bool:
        """True when the two stays share at least one night.

        This is the only place where the overlap rule is written (R3).
        Strict ``<`` on both sides implements the half-open rule:
        12-14 and 14-16 do not overlap, 12-14 and 13-15 do.
        """
        return self.check_in < other.check_out and other.check_in < self.check_out


@dataclass(frozen=True)
class Guest:
    """The person the room is booked for."""

    name: str
    email: str


class ReservationStatus(Enum):
    """The only two states a reservation can be in (version 1)."""

    CONFIRMED = "Confirmed"
    CANCELLED = "Cancelled"


class Reservation:
    """One booking of one room for one stay by one guest.

    Composition: the reservation owns its ``stay`` (a ``DateRange``).
    Association: it only refers to its ``guest`` and ``room``, which exist
    before and after it.
    """

    def __init__(self, reservation_id: str, guest: Guest, room: Room, stay: DateRange) -> None:
        self._id = reservation_id
        self._guest = guest
        self._room = room
        self._stay = stay
        self._status = ReservationStatus.CONFIRMED

    # Read-only views: the identity and facts never change after creation,
    # and the status changes only through cancel() (encapsulation).
    @property
    def id(self) -> str:
        return self._id

    @property
    def guest(self) -> Guest:
        return self._guest

    @property
    def room(self) -> Room:
        return self._room

    @property
    def stay(self) -> DateRange:
        return self._stay

    @property
    def status(self) -> ReservationStatus:
        return self._status

    def blocks(self, room: Room, stay: DateRange) -> bool:
        """True when this reservation prevents booking ``room`` for ``stay``.

        Only a Confirmed reservation of the same room that shares a night blocks.
        """
        return (
            self._status is ReservationStatus.CONFIRMED
            and self._room == room
            and self._stay.overlaps(stay)
        )

    def cancel(self) -> bool:
        """Confirmed -> Cancelled. Returns False (and changes nothing) if already Cancelled."""
        if self._status is ReservationStatus.CANCELLED:
            return False
        self._status = ReservationStatus.CANCELLED
        return True

    def __repr__(self) -> str:
        return (
            f"Reservation({self._id!r}, guest={self._guest.name!r}, room={self._room.number!r}, "
            f"stay={self._stay.check_in.isoformat()}..{self._stay.check_out.isoformat()}, "
            f"status={self._status.value})"
        )
