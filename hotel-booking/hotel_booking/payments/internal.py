"""Payments' internal code. Only Payments, the wiring and tests import this."""
from __future__ import annotations

from decimal import Decimal

from hotel_booking.payments import PaymentStatus


class SimulatedPaymentService:
    """Simulated: no card, no provider, no network. A positive amount is Paid; anything else is Declined.

    Keeps the ``PaymentService`` promise by shape. It also remembers what it
    took, so a test (and later the P17 saga) can see the deposits.
    """

    def __init__(self) -> None:
        self.taken: list[tuple[str, Decimal]] = []

    def take_deposit(self, reservation_id: str, amount: Decimal) -> PaymentStatus:
        if amount > 0:
            self.taken.append((reservation_id, amount))
            return PaymentStatus.PAID
        return PaymentStatus.DECLINED
