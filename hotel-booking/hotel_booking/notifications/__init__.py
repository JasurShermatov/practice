"""Notifications: telling guests what happened.

Public contract: ``Confirmation``, ``NotificationSender`` and - since P10 - what a queued sender
reports: ``NotificationCounts`` (the counters of GET /stats), ``DeliveryStatus`` (what became of one
guest's confirmation) and ``ConfirmationRefused`` (a confirmation that will not be sent).

The P05 border "Reservations -> Notifications: ReservationConfirmed" in code. In P06 it was a
method call that ran inside the booking request. In P10 the same call hands the confirmation to a
bounded queue drained by background workers (``internal.QueuedNotificationSender``); the promise
below did not change, so Reservations did not change either.

Notifications depends on no other module (architecture rule 3, and since P10 the contract
"Notifications depends on no other module"): it receives its own ``Confirmation`` message instead
of the ``Reservation`` class, so the two modules cannot form a dependency circle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol


@dataclass(frozen=True)
class Confirmation:
    """Notifications' own message: exactly the five fields that cross the border (P05 "Between contexts").

    Frozen and made of plain values, so a sender can neither change the
    booking nor reach Reservations' rows through it (rule card 8). Being immutable is also what
    makes it safe to hand from a request thread to a worker thread (P10).
    """

    reservation_id: str
    guest_email: str
    room_number: str
    check_in: date
    check_out: date


class NotificationSender(Protocol):
    """Notifications' public promise: "give me a Confirmation and I will tell the guest"."""

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """Tell the guest - now, or later from a queue. May raise if the message will not be sent
        (the caller keeps the booking, R6)."""
        ...


class ConfirmationRefused(Exception):
    """The confirmation will not be sent: the queue was full or the app is shutting down (P10).

    Raised by the request-scoped sender the wiring gives each booking request, *before* the
    booking commits, so ``BookingService`` reports it the R6 way: the reservation stays saved and
    Accepted, and the answer says ``notificationFailed: true``. The queue itself never raises.
    """


class DeliveryStatus(Enum):
    """What became of one guest's confirmation (P10). Every confirmation ends in exactly one of the
    last four; QUEUED and SENDING are the two states on the way."""

    QUEUED = "queued"        # accepted, waiting for a worker
    SENDING = "sending"      # a worker has taken it and is talking to the mail server
    SENT = "sent"            # the sender returned: done
    FAILED = "failed"        # every allowed attempt raised (or timed out); not retried any more
    REJECTED = "rejected"    # refused at the door: the queue was full or closing
    DROPPED = "dropped"      # accepted, then cancelled by a shutdown that did not finish the queue


@dataclass(frozen=True)
class NotificationCounts:
    """What a queued sender has promised, refused, finished and still owes.

    The course's four counters - ``accepted``, ``rejected``, ``completed``, ``queued`` - plus
    ``failed`` (sends that gave up after every attempt) and ``dropped`` (accepted jobs cancelled by
    a shutdown; always 0 while the app serves requests). Every accepted job ends in exactly one of
    completed, failed or dropped, so once nothing is in flight::

        accepted == completed + failed + dropped + queued

    and while workers are busy the difference (``in_flight``) is at most one job per worker. If the
    two sides ever differ by more, work went missing, and these counters are where it would show.
    """

    accepted: int
    rejected: int
    completed: int
    queued: int
    failed: int = 0
    dropped: int = 0

    @property
    def in_flight(self) -> int:
        """Jobs a worker has taken off the queue and not finished yet."""
        return self.accepted - self.completed - self.failed - self.dropped - self.queued


__all__ = ["Confirmation", "ConfirmationRefused", "DeliveryStatus", "NotificationCounts", "NotificationSender"]
