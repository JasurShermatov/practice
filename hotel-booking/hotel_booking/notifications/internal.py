"""Notifications' internal code: how a message travels. Only Notifications, the wiring and tests import this.

Both senders are simulated: they count what they would send and need no
network, mail server or SMS gateway. Replacing them with a real channel (or a
queue in P10/P15) changes this file and the wiring, never Reservations.
"""
from __future__ import annotations

from hotel_booking.notifications import Confirmation


class EmailNotificationSender:
    """Simulated email; keeps the ``NotificationSender`` promise by shape."""

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """'Send' the confirmation email for ``confirmation.reservation_id``."""
        self.sent += 1


class SmsNotificationSender:
    """Simulated SMS (P04 Step 7); same promise as the email sender, so the wiring can pick either."""

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, confirmation: Confirmation) -> None:
        """'Send' the confirmation text message for ``confirmation.reservation_id``."""
        self.sent += 1
