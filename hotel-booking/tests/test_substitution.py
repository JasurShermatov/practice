"""Liskov substitution and the course's completed example (P04).

"Replace the vendor dependency with a port implemented by an adapter. Visible
result: the booking rule remains unchanged when the provider changes. Saved
data: accepted booking records stay the same."

Every sender and every store that keeps its promise must give BookingService
exactly the same answers and the same saved records. A second store written
here (a dict instead of a list) shows that the storage promise, not the list,
is what BookingService relies on - the same move P07 makes with PostgreSQL.

P06 change (deliberate): imports come from the modules. The P04 counter-example
``CancellingSender`` (right method name, but it cancelled the booking it was
given) cannot be written any more: since P06 a sender receives a frozen
``Confirmation`` with five plain fields, not the ``Reservation``. Its test now
shows that such a sender is *contained* (R6 keeps the booking and the records
stay identical), and a store that breaks its promise is the new counter-example
showing that the scenario still catches a bad substitute.

P09 change (deliberate): the ``ReservationStore`` promise grew (``next_reservation_id``; ``save``
refuses an overlap with ``OverlapRejected``), so the tests-only ``DictReservationStore`` keeps the
new promise too - a substitute must keep the whole promise, including the part that only matters
under concurrency. ``scenario`` reports a missing record as text instead of failing inside the
helper, so the counter-example (``ForgetfulStore``) is still told apart by comparison. New: a store
that forgets the overlap promise (the version-5 ``save``) gives the same one-at-a-time answers -
which is exactly why the P09 concurrency tests exist.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from hotel_booking.notifications import Confirmation, NotificationSender
from hotel_booking.notifications.internal import EmailNotificationSender, SmsNotificationSender
from hotel_booking.reservations import BookingService, DateRange, OverlapRejected, Reservation, ReservationStore
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room
from hotel_booking.demo import HOTEL_ROOMS, MAYA, NORA, OMAR, R7, R8, nov
from test_booking_service import FakeNotificationSender


class DictReservationStore:
    """Tests only: a second way to keep the ReservationStore promise (rows in a dict by id)."""

    def __init__(self) -> None:
        self._by_id: dict[str, Reservation] = {}
        self._issued = 100

    def count(self) -> int:
        return len(self._by_id)

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return any(row.blocks(room, stay) for row in self._by_id.values())

    def next_reservation_id(self) -> str:
        self._issued += 1  # single-threaded tests only: no lock needed here
        return f"R{self._issued}"

    def save(self, reservation: Reservation) -> None:
        if self.has_overlap(reservation.room, reservation.stay):
            raise OverlapRejected(f"{reservation.room.number} is taken")
        self._by_id[reservation.id] = reservation

    def find(self, reservation_id: str) -> Reservation | None:
        return self._by_id.get(reservation_id)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return sum(1 for row in self._by_id.values() if row.blocks(room, stay))


class MeddlingSender:
    """A BAD sender: right method name, but it tries to change what it was given (P04's CancellingSender).

    In P04 it received the Reservation and could cancel it. Since P06 it only
    gets a frozen Confirmation, so the attempt raises and R6 contains it.
    """

    def send_confirmation(self, confirmation: Confirmation) -> None:
        confirmation.reservation_id = "R999"  # type: ignore[misc]  # frozen: raises FrozenInstanceError


class ForgetfulStore(InMemoryReservationStore):
    """A BAD store: keeps the method names, but ``save`` forgets every second reservation."""

    def __init__(self) -> None:
        super().__init__()
        self._calls = 0

    def save(self, reservation: Reservation) -> None:
        self._calls += 1
        if self._calls % 2:
            super().save(reservation)


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
        records.append(f"R{number} missing" if row is None else
                       f"{row.id} {row.guest.name} {row.room.number} {row.stay} {row.status.value}")
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


def test_a_sender_can_no_longer_change_the_booking() -> None:
    """P06: the border carries a frozen Confirmation, so a meddling sender cannot touch Reservations' data."""
    assert scenario(InMemoryReservationStore(), MeddlingSender()) == EXPECTED  # contained by R6
    service = BookingService(HOTEL_ROOMS, InMemoryReservationStore(), MeddlingSender())
    result = service.reserve(MAYA, R7, nov(12, 14))
    assert (str(result), result.notification_failed) == ("Accepted R101", True)


def test_a_store_that_breaks_the_promise_is_caught() -> None:
    """Liskov: same method names, but saves are lost - the scenario no longer matches."""
    assert scenario(ForgetfulStore(), FakeNotificationSender()) != EXPECTED


class PromiseForgettingStore(InMemoryReservationStore):
    """A BAD store under concurrency only: the version-5 ``save`` (append, no check, no lock)."""

    def save(self, reservation: Reservation) -> None:
        self._rows.append(reservation)


def test_a_store_that_forgets_the_overlap_promise_passes_one_at_a_time_and_fails_under_pressure() -> None:
    """Why P09 needs its own tests: one request at a time, this bad store is indistinguishable."""
    assert scenario(PromiseForgettingStore(), FakeNotificationSender()) == EXPECTED
    bad, good = PromiseForgettingStore(), InMemoryReservationStore()
    bad.save(Reservation("R101", MAYA, R7, nov(12, 14)))
    good.save(Reservation("R101", MAYA, R7, nov(12, 14)))
    bad.save(Reservation("R102", OMAR, R7, nov(13, 15)))  # what a request that lost the race would do
    with pytest.raises(OverlapRejected):
        good.save(Reservation("R102", OMAR, R7, nov(13, 15)))
    assert (bad.count_confirmed(R7, nov(12, 15)), good.count_confirmed(R7, nov(12, 15))) == (2, 1)


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
