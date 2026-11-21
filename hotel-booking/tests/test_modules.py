"""The new P06 contracts: Rooms' catalog, Payments' deposit, Notifications' own Confirmation message.

The 8 P04 tests prove the move kept behaviour; these tests pin what P06 adds:

- Rooms: the catalog keeps the ``RoomCatalog`` promise and hands out copies.
- Payments: a positive Decimal amount is Paid, zero or negative is Declined.
- Notifications: BookingService translates a saved reservation into exactly the
  five P05 border fields, and a sender can no longer reach the Reservation.
"""
from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from hotel_booking.demo import HOTEL_ROOMS, MAYA, OMAR, R7, R8, nov
from hotel_booking.notifications import Confirmation, NotificationSender
from hotel_booking.notifications.internal import EmailNotificationSender, SmsNotificationSender
from hotel_booking.payments import PaymentService, PaymentStatus
from hotel_booking.payments.internal import SimulatedPaymentService
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room, RoomCatalog
from hotel_booking.rooms.internal import InMemoryRoomCatalog


class RecordingSender:
    """Tests only: keeps every Confirmation it is given."""

    def __init__(self) -> None:
        self.received: list[Confirmation] = []

    def send_confirmation(self, confirmation: Confirmation) -> None:
        self.received.append(confirmation)


# --- Rooms ------------------------------------------------------------------------------


def test_catalog_lists_the_hotels_rooms_in_order() -> None:
    catalog: RoomCatalog = InMemoryRoomCatalog(HOTEL_ROOMS)
    assert catalog.all() == [R7, R8]


def test_catalog_hands_out_a_copy() -> None:
    catalog = InMemoryRoomCatalog(HOTEL_ROOMS)
    rooms = catalog.all()
    rooms.append(Room("R9", "Suite"))
    assert catalog.all() == [R7, R8]


def test_booking_service_offers_exactly_the_catalogs_rooms() -> None:
    """The wiring passes catalog.all(); a room taken off the catalog is no longer offered (rule card 4's seam)."""
    only_r8 = InMemoryRoomCatalog([R8])
    service = BookingService(only_r8.all(), InMemoryReservationStore(), RecordingSender())
    assert service.find_free_rooms(nov(12, 14)) == [R8]


# --- Payments ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [(Decimal("60.00"), PaymentStatus.PAID), (Decimal("0.01"), PaymentStatus.PAID),
     (Decimal("0"), PaymentStatus.DECLINED), (Decimal("-5"), PaymentStatus.DECLINED)],
)
def test_simulated_payment_pays_only_a_positive_amount(amount: Decimal, expected: PaymentStatus) -> None:
    payments: PaymentService = SimulatedPaymentService()
    assert payments.take_deposit("R101", amount) is expected


def test_simulated_payment_remembers_only_what_it_took() -> None:
    payments = SimulatedPaymentService()
    payments.take_deposit("R101", Decimal("60.03"))
    payments.take_deposit("R102", Decimal("0"))
    assert payments.taken == [("R101", Decimal("60.03"))]


def test_deposit_arithmetic_is_exact_with_decimal() -> None:
    """Why the contract uses Decimal (P05): 30% of 200.10 is 60.03, which float cannot hold."""
    assert Decimal("200.10") * Decimal("0.30") == Decimal("60.0300")
    assert 200.10 * 0.30 != 60.03


# --- Notifications ----------------------------------------------------------------------


def test_reservations_sends_the_five_border_fields() -> None:
    sender = RecordingSender()
    service = BookingService(HOTEL_ROOMS, InMemoryReservationStore(), sender)
    service.reserve(MAYA, R7, nov(12, 14))
    service.reserve(OMAR, R7, nov(13, 15))  # refused: nothing sent
    assert sender.received == [
        Confirmation("R101", "maya@example.com", "R7", date(2026, 11, 12), date(2026, 11, 14)),
    ]


def test_confirmation_is_exactly_the_p05_fields_and_frozen() -> None:
    fields = [field.name for field in dataclasses.fields(Confirmation)]
    assert fields == ["reservation_id", "guest_email", "room_number", "check_in", "check_out"]
    message = Confirmation("R101", "maya@example.com", "R7", date(2026, 11, 12), date(2026, 11, 14))
    with pytest.raises(dataclasses.FrozenInstanceError):
        message.room_number = "R8"  # type: ignore[misc]


@pytest.mark.parametrize("sender_class", [EmailNotificationSender, SmsNotificationSender])
def test_both_senders_keep_the_notifications_promise(sender_class: type[EmailNotificationSender]) -> None:
    sender = sender_class()
    promise: NotificationSender = sender  # mypy checks the shape here
    promise.send_confirmation(Confirmation("R101", "maya@example.com", "R7", date(2026, 11, 12), date(2026, 11, 14)))
    assert sender.sent == 1
    assert sender_class.__module__ == "hotel_booking.notifications.internal"
