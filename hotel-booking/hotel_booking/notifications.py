"""Confirmation messages (P03: simulated email).

The sender only counts what it would send; it needs no network or mail server.
P04 moves this dependency behind an interface so BookingService stops
depending on a concrete email class.
"""
from __future__ import annotations

from .domain import Reservation


class EmailSender:
    """Simulated email sender: records each confirmation instead of sending it."""

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, reservation: Reservation) -> None:
        """'Send' the confirmation for a saved reservation."""
        self.sent += 1
