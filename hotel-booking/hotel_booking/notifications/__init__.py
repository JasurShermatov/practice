"""Notifications: telling guests what happened. Public contract: ``Confirmation`` and ``NotificationSender``.

The P05 border "Reservations -> Notifications: ReservationConfirmed" in code. In
P06 it is a method call; from P10/P15 it becomes a queued message, and only the
internal code here changes.

Notifications depends on no other module, in particular never on Reservations
(architecture rule 3): it receives its own ``Confirmation`` message instead of
the ``Reservation`` class, so the two modules cannot form a dependency circle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Confirmation:
    """Notifications' own message: exactly the five fields that cross the border (P05 "Between contexts").

    Frozen and made of plain values, so a sender can neither change the
    booking nor reach Reservations' rows through it (rule card 8).
    """

    reservation_id: str
    guest_email: str
    room_number: str
    check_in: date
    check_out: date


class NotificationSender(Protocol):
    """Notifications' public promise: "give me a Confirmation and I will tell the guest"."""

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """Tell the guest. May raise if the message cannot be sent (the caller keeps the booking, R6)."""
        ...


__all__ = ["Confirmation", "NotificationSender"]
