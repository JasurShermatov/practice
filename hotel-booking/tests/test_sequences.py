"""The message order of the sequence diagrams, checked against the running code.

Spies record every call that crosses an object boundary, so each test reads
like the numbered arrows of the matching diagram in
practices/P03-hotel-domain-uml/uml/ (sequence-book, sequence-unavailable,
sequence-cancel) and practices/P04-refactor-reservation/uml/
(sequence-r6-failed-confirmation).

P04 change (deliberate): the spies now extend the renamed concrete classes
(InMemoryReservationStore, EmailNotificationSender) - the P03 message order is
unchanged, which is part of the proof that the refactoring kept behaviour.

P06 change (deliberate): imports come from the modules, and the senders now
receive Notifications' own ``Confirmation`` instead of the ``Reservation``, so
the spies log ``confirmation.reservation_id``. Every expected log is unchanged.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from hotel_booking.notifications import Confirmation
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, DateRange, Reservation
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.demo import HOTEL_ROOMS, MAYA, OMAR, R7, nov

Log = list[str]


@dataclass(frozen=True)
class SpyDateRange(DateRange):
    log: Log | None = None

    def is_valid(self) -> bool:
        answer = super().is_valid()
        assert self.log is not None
        self.log.append(f"stay.is_valid() -> {answer}")
        return answer


class SpyStore(InMemoryReservationStore):
    def __init__(self, log: Log) -> None:
        super().__init__()
        self.log = log

    def has_overlap(self, room, stay):  # type: ignore[no-untyped-def]
        answer = super().has_overlap(room, stay)
        self.log.append(f"store.has_overlap({room.number}) -> {answer}")
        return answer

    def count(self) -> int:
        answer = super().count()
        self.log.append(f"store.count() -> {answer}")
        return answer

    def save(self, reservation: Reservation) -> None:
        self.log.append(f"store.save({reservation.id})")
        super().save(reservation)

    def find(self, reservation_id: str):  # type: ignore[no-untyped-def]
        answer = super().find(reservation_id)
        self.log.append(f"store.find({reservation_id}) -> {answer.id if answer else None}")
        return answer


class SpyEmail(EmailNotificationSender):
    def __init__(self, log: Log) -> None:
        super().__init__()
        self.log = log

    def send_confirmation(self, confirmation: Confirmation) -> None:
        self.log.append(f"email.send_confirmation({confirmation.reservation_id})")
        super().send_confirmation(confirmation)


def spied(log: Log, check_in: int, check_out: int) -> SpyDateRange:
    plain = nov(check_in, check_out)
    return SpyDateRange(plain.check_in, plain.check_out, log)


def new_service(log: Log) -> tuple[BookingService, SpyStore]:
    store = SpyStore(log)
    return BookingService(HOTEL_ROOMS, store, SpyEmail(log)), store


def test_sequence_book_maya_r7() -> None:
    log: Log = []
    service, _ = new_service(log)
    result = service.reserve(MAYA, R7, spied(log, 12, 14))
    log.append(f"reply -> {result}")
    assert log == [
        "stay.is_valid() -> True",
        "store.has_overlap(R7) -> False",
        "store.count() -> 0",
        "store.save(R101)",
        "email.send_confirmation(R101)",
        "reply -> Accepted R101",
    ]


def test_sequence_unavailable_omar_r7() -> None:
    log: Log = []
    service, _ = new_service(log)
    service.reserve(MAYA, R7, nov(12, 14))
    log.clear()
    result = service.reserve(OMAR, R7, spied(log, 13, 15))
    log.append(f"reply -> {result}")
    assert log == [
        "stay.is_valid() -> True",
        "store.has_overlap(R7) -> True",
        "reply -> Unavailable",
    ]  # no count, no save, no email


def test_sequence_invalid_dates_stops_before_the_store() -> None:
    log: Log = []
    service, _ = new_service(log)
    result = service.reserve(OMAR, R7, spied(log, 15, 15))
    log.append(f"reply -> {result}")
    assert log == ["stay.is_valid() -> False", "reply -> InvalidDates"]


def test_sequence_cancel_r101() -> None:
    log: Log = []
    service, store = new_service(log)
    service.reserve(MAYA, R7, nov(12, 14))
    r101 = InMemoryReservationStore.find(store, "R101")  # unspied lookup for the test setup
    assert r101 is not None
    real_cancel = r101.cancel

    def spy_cancel() -> bool:
        answer = real_cancel()
        log.append(f"R101.cancel() -> {answer}")
        return answer

    r101.cancel = spy_cancel  # type: ignore[method-assign]
    log.clear()
    answer = service.cancel("R101")
    log.append(f"reply -> {answer}")
    assert log == ["store.find(R101) -> R101", "R101.cancel() -> True", "reply -> True"]
    assert r101.status.value == "Cancelled"


def test_sequence_race_both_checks_before_either_save() -> None:
    """The message order of uml/sequence-race: check, check, save, save (R3 broken, fixed in P09)."""
    log: Log = []
    store = SpyStore(log)
    service = BookingService(HOTEL_ROOMS, store, SpyEmail(log), slow_step_seconds=0.3)
    maya = threading.Thread(target=service.reserve, args=(MAYA, R7, nov(12, 14)))
    omar = threading.Thread(target=service.reserve, args=(OMAR, R7, nov(12, 14)))
    maya.start()
    time.sleep(0.05)
    omar.start()
    maya.join()
    omar.join()
    assert log == [
        "store.has_overlap(R7) -> False",  # Maya checks
        "store.has_overlap(R7) -> False",  # Omar checks before Maya saved
        "store.count() -> 0",
        "store.save(R101)",
        "email.send_confirmation(R101)",
        "store.count() -> 1",
        "store.save(R102)",
        "email.send_confirmation(R102)",
    ]


class FailingSpySender:
    """Keeps the NotificationSender promise, logs the call, then fails like a mail server that is down."""

    def __init__(self, log: Log) -> None:
        self.log = log

    def send_confirmation(self, confirmation: Confirmation) -> None:
        self.log.append(f"sender.send_confirmation({confirmation.reservation_id}) -> error")
        raise RuntimeError("The mail server is down.")


def test_sequence_r6_failed_confirmation() -> None:
    """uml/sequence-r6-failed-confirmation: save (4) happens before the failing send (5-6)."""
    log: Log = []
    store = SpyStore(log)
    service = BookingService(HOTEL_ROOMS, store, FailingSpySender(log))
    result = service.reserve(MAYA, R7, nov(12, 14))
    log.append(f"reply -> {result} (notification_failed={result.notification_failed})")
    assert log == [
        "store.has_overlap(R7) -> False",
        "store.count() -> 0",
        "store.save(R101)",
        "sender.send_confirmation(R101) -> error",
        "reply -> Accepted R101 (notification_failed=True)",
    ]
    saved = InMemoryReservationStore.find(store, "R101")
    assert saved is not None and saved.status.value == "Confirmed"  # not undone
