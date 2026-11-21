"""How the guest is told about a booking (P04: a promise and the classes that keep it).

``NotificationSender`` is the *promise* (a ``typing.Protocol``, Python's
interface): "you can ask me to confirm a reservation". ``BookingService``
depends only on this promise, so how the message travels - email, SMS, a fake
in the tests - is decided by whoever builds the service (``main.py``).

The senders here are simulated: they count what they would send and need no
network, mail server or SMS gateway.
"""
from __future__ import annotations

from typing import Protocol

from .domain import Reservation


class NotificationSender(Protocol):
    """What BookingService needs from messaging: "tell the guest". One method, nothing else (I in SOLID)."""

    def send_confirmation(self, reservation: Reservation) -> None:
        """Tell the guest that ``reservation`` is saved. May raise if the message cannot be sent."""
        ...


class EmailNotificationSender:
    """Simulated email (was ``EmailSender`` in P03): records each confirmation instead of sending it.

    Keeps the ``NotificationSender`` promise by shape: it has ``send_confirmation``.
    """

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, reservation: Reservation) -> None:
        """'Send' the confirmation email for a saved reservation."""
        self.sent += 1


class SmsNotificationSender:
    """Simulated SMS, added in P04 Step 7 *without changing BookingService* (O in SOLID).

    Keeps the same ``NotificationSender`` promise as the email sender, so
    ``main.py`` can pass either one in.
    """

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, reservation: Reservation) -> None:
        """'Send' the confirmation text message for a saved reservation."""
        self.sent += 1
