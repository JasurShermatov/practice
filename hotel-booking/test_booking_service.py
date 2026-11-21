"""Tests for the booking service after the P04 refactoring (Step 2 tests + Step 7).

The first six are the Step 2 characterization tests: they passed on the P03
code and still pass after every refactoring move. Since Step 7 they run with a
fake sender, so the sixth test can check exactly which reservations were
confirmed.

Run them from the hotel-booking folder:  python -m unittest -v
"""
from __future__ import annotations

import unittest
from datetime import date

from hotel_booking import (
    BookingService,
    DateRange,
    Guest,
    InMemoryReservationStore,
    Reservation,
    Room,
    SmsNotificationSender,
)

R7 = Room("R7", "Standard")
R8 = Room("R8", "Deluxe")
MAYA = Guest("Maya", "maya@example.com")
OMAR = Guest("Omar", "omar@example.com")
NORA = Guest("Nora", "nora@example.com")


def nov(check_in: int, check_out: int) -> DateRange:
    """A stay in November 2026: ``nov(12, 14)`` is the nights of the 12th and 13th."""
    return DateRange(date(2026, 11, check_in), date(2026, 11, check_out))


class FakeNotificationSender:
    """Tests only: keeps the NotificationSender promise, remembers what it would send, or fails on purpose."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[str] = []

    def send_confirmation(self, reservation: Reservation) -> None:
        if self.fail:
            raise RuntimeError("The mail server is down.")
        self.sent.append(reservation.id)


def new_service(
    failing_sender: bool = False,
) -> tuple[BookingService, InMemoryReservationStore, FakeNotificationSender]:
    """The only place that builds the service: after the refactoring it takes any sender."""
    store = InMemoryReservationStore()
    sender = FakeNotificationSender(fail=failing_sender)
    return BookingService([R7, R8], store, sender), store, sender


class BookingServiceTests(unittest.TestCase):
    def test_maya_gets_r7_when_it_is_free(self) -> None:
        service, _, _ = new_service()
        self.assertEqual("Accepted R101", str(service.reserve(MAYA, R7, nov(12, 14))))

    def test_omar_is_refused_when_a_night_is_shared(self) -> None:
        service, store, _ = new_service()                     # Arrange
        service.reserve(MAYA, R7, nov(12, 14))
        result = service.reserve(OMAR, R7, nov(13, 15))       # Act
        self.assertEqual("Unavailable", str(result))          # Assert
        self.assertEqual(1, store.count())

    def test_nora_can_arrive_on_the_day_maya_leaves(self) -> None:
        service, _, _ = new_service()
        service.reserve(MAYA, R7, nov(12, 14))
        self.assertEqual("Accepted R102", str(service.reserve(NORA, R7, nov(14, 16))))

    def test_check_out_must_be_after_check_in(self) -> None:
        service, store, _ = new_service()
        self.assertEqual("InvalidDates", str(service.reserve(OMAR, R8, nov(15, 15))))
        self.assertEqual(0, store.count())

    def test_cancelling_frees_the_room_again(self) -> None:
        service, _, _ = new_service()
        service.reserve(MAYA, R7, nov(12, 14))
        self.assertTrue(service.cancel("R101"))
        self.assertIn(R7, service.find_free_rooms(nov(12, 14)))

    def test_one_confirmation_per_accepted_booking(self) -> None:
        service, _, sender = new_service()
        service.reserve(MAYA, R7, nov(12, 14))
        service.reserve(OMAR, R7, nov(13, 15))   # refused: no confirmation
        service.reserve(NORA, R7, nov(14, 16))
        self.assertEqual(["R101", "R102"], sender.sent)

    def test_a_failed_confirmation_keeps_the_booking(self) -> None:
        """R6: the sender fails after the save; the booking stays saved and Accepted, the failure is reported."""
        service, store, _ = new_service(failing_sender=True)
        with self.assertLogs("hotel_booking.booking", level="WARNING") as log:  # reported ...
            result = service.reserve(MAYA, R7, nov(12, 14))
        self.assertEqual("Accepted R101", str(result))
        self.assertTrue(result.notification_failed)                             # ... in the result too
        self.assertEqual(1, store.count())
        self.assertIn("R101", log.output[0])

    def test_sms_confirmations_need_no_change_to_booking_service(self) -> None:
        sms = SmsNotificationSender()
        service = BookingService([R7, R8], InMemoryReservationStore(), sms)
        service.reserve(MAYA, R7, nov(12, 14))
        self.assertEqual(1, sms.sent)


if __name__ == "__main__":
    unittest.main()
