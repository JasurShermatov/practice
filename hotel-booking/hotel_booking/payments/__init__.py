"""Payments: deposits and whether they were paid. Public contract: ``PaymentStatus`` and ``PaymentService``.

Nothing calls Payments yet: the booking saga takes the deposit in P17. The
module exists now so that its border is real and tested from the start.
Payments owns the money rules (rule cards 6 and 7: the 30% deposit, refunds);
when they arrive they are written here, never in Reservations.

Money is ``decimal.Decimal`` (P05 recommendation): 30% of 200.10 must be
60.03, not 60.029999...

Payments depends on no other module, in particular never on Reservations
(architecture rule 3): it receives a reservation id and an amount, not a
``Reservation``.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Protocol


class PaymentStatus(Enum):
    """The two answers to "take a deposit"."""

    PAID = "Paid"
    DECLINED = "Declined"


class PaymentService(Protocol):
    """Payments' public promise: take a deposit for a reservation and say whether it was paid."""

    def take_deposit(self, reservation_id: str, amount: Decimal) -> PaymentStatus:
        """Try to take ``amount`` for ``reservation_id``; never raises for a refusal, answers DECLINED."""
        ...


__all__ = ["PaymentService", "PaymentStatus"]
