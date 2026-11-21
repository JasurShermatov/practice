"""Liskov substitution and the course's completed example (P04).

"Replace the vendor dependency with a port implemented by an adapter. Visible
result: the booking rule remains unchanged when the provider changes. Saved
data: accepted booking records stay the same."

Every sender and every store that keeps its promise must give BookingService
exactly the same answers and the same saved records. A second store written
here (a dict instead of a list) shows that the storage promise, not the list,
is what BookingService relies on - the same move P07 makes with PostgreSQL.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from hotel_booking import (
    BookingService,
    DateRange,
    EmailNotificationSender,
    InMemoryReservationStore,
    NotificationSender,
    Reservation,
    ReservationStore,
    Room,
    SmsNotificationSender,
)
from hotel_booking.demo import HOTEL_ROOMS, MAYA, NORA, OMAR, R7, R8, nov
from test_booking_service import FakeNotificationSender


class DictReservationStore:
    """Tests only: a second way to keep the ReservationStore promise (rows in a dict by id)."""

    def __init__(self) -> None:
        self._by_id: dict[str, Reservation] = {}

    def count(self) -> int:
        return len(self._by_id)

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return any(row.blocks(room, stay) for row in self._by_id.values())

    def save(self, reservation: Reservation) -> None:
        self._by_id[reservation.id] = reservation

    def find(self, reservation_id: str) -> Reservation | None:
        return self._by_id.get(reservation_id)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return sum(1 for row in self._by_id.values() if row.blocks(room, stay))


class CancellingSender:
    """A BAD sender (the activity sheet's Liskov counter-example): right method name, wrong promise."""

    def send_confirmation(self, reservation: Reservation) -> None:
        reservation.cancel()


SENDERS: dict[str, Callable[[], NotificationSender]] = {
    "email": EmailNotificationSender,
    "sms": SmsNotificationSender,
    "fake": FakeNotificationSender,
}
STORES: dict[str, Callable[[], ReservationStore]] = {
    "in-memory list": InMemoryReservationStore,
    "dict (tests only)": DictReservationStore,
}


def scenario(store: ReservationStore, sender: NotificationSender) -> list[str]:
    """Accepted, full and error cases, then every saved record, as text."""
    service = BookingService(HOTEL_ROOMS, store, sender)
    answers = [
        str(service.reserve(MAYA, R7, nov(12, 14))),   # accepted
        str(service.reserve(OMAR, R7, nov(13, 15))),   # full: shares the 13th
        str(service.reserve(NORA, R7, nov(14, 16))),   # accepted: adjacent
        str(service.reserve(OMAR, R8, nov(15, 15))),   # error: zero nights
        str(service.reserve(OMAR, R8, nov(12, 14))),   # accepted
        ", ".join(room.number for room in service.find_free_rooms(nov(12, 14))) or "full",
        str(service.cancel("R101")),
        ", ".join(room.number for room in service.find_free_rooms(nov(12, 14))) or "full",
    ]
    records = []
    for number in range(101, 101 + store.count()):
        row = store.find(f"R{number}")
        assert row is not None
        records.append(f"{row.id} {row.guest.name} {row.room.number} {row.stay} {row.status.value}")
    return answers + records


EXPECTED = scenario(InMemoryReservationStore(), EmailNotificationSender())  # the app's own wiring


def test_expected_scenario_is_the_p03_behaviour() -> None:
    assert EXPECTED[:8] == [
        "Accepted R101", "Unavailable", "Accepted R102", "InvalidDates", "Accepted R103",
        "full", "True", "R7",
    ]
    assert [record.split()[-1] for record in EXPECTED[8:]] == ["Cancelled", "Confirmed", "Confirmed"]


@pytest.mark.parametrize("sender_name", SENDERS)
def test_changing_the_provider_keeps_answers_and_saved_records(sender_name: str) -> None:
    assert scenario(InMemoryReservationStore(), SENDERS[sender_name]()) == EXPECTED


@pytest.mark.parametrize("store_name", STORES)
def test_changing_the_store_keeps_answers_and_saved_records(store_name: str) -> None:
    assert scenario(STORES[store_name](), FakeNotificationSender()) == EXPECTED


def test_a_sender_that_breaks_the_promise_is_caught() -> None:
    """Liskov: same method name, but it cancels the booking - the scenario no longer matches."""
    assert scenario(InMemoryReservationStore(), CancellingSender()) != EXPECTED


def test_after_a_failed_confirmation_the_room_stays_taken() -> None:
    """R6 together with R3: the saved-but-unconfirmed booking still blocks R7 for others."""
    service = BookingService(HOTEL_ROOMS, InMemoryReservationStore(), FakeNotificationSender(fail=True))
    first = service.reserve(MAYA, R7, nov(12, 14))
    assert (str(first), first.notification_failed) == ("Accepted R101", True)
    assert str(service.reserve(OMAR, R7, nov(13, 15))) == "Unavailable"
    assert service.find_free_rooms(nov(12, 14)) == [R8]


def test_a_successful_confirmation_is_not_reported_as_failed() -> None:
    service = BookingService(HOTEL_ROOMS, InMemoryReservationStore(), FakeNotificationSender())
    assert service.reserve(MAYA, R7, nov(12, 14)).notification_failed is False
    assert service.reserve(OMAR, R7, nov(13, 15)).notification_failed is False  # refused: nothing sent
