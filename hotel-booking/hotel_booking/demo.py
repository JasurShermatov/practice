"""The classroom scenario: rooms R7/R8 and guests Maya, Omar and Nora (fictional).

``run_demo`` prints the nine lines that prove R1-R4; ``run_race`` shows the
double booking that P09 fixes.

Since P04 these functions *receive* the service and its helpers instead of
creating them: ``main.py`` is the composition root, the only place that picks
the real store and sender. The scenario itself did not change.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from datetime import date

from .booking import BookingResult, BookingService
from .domain import DateRange, Guest, Room
from .notifications import EmailNotificationSender
from .stores import ReservationStore

R7 = Room("R7", "Standard")
R8 = Room("R8", "Deluxe")
HOTEL_ROOMS = (R7, R8)

MAYA = Guest("Maya", "maya@example.com")
OMAR = Guest("Omar", "omar@example.com")
NORA = Guest("Nora", "nora@example.com")

DEMO_YEAR = 2026


def nov(check_in: int, check_out: int) -> DateRange:
    """A stay in November of the demo year, e.g. ``nov(12, 14)`` = nights of the 12th and 13th."""
    return DateRange(date(DEMO_YEAR, 11, check_in), date(DEMO_YEAR, 11, check_out))


def room_numbers(rooms: Iterable[Room]) -> str:
    return ", ".join(room.number for room in rooms)


def run_demo(service: BookingService, email: EmailNotificationSender) -> None:
    """The normal demo: one request at a time.

    ``email`` is the sender that ``service`` was built with; it is passed in only
    so the last line can report how many confirmations it counted.
    """
    print(f"Free rooms 12-14 Nov: {room_numbers(service.find_free_rooms(nov(12, 14)))}")
    print(f"Maya books R7 12-14 Nov: {service.reserve(MAYA, R7, nov(12, 14))}")
    print(f"Omar books R7 13-15 Nov: {service.reserve(OMAR, R7, nov(13, 15))}")
    print(f"Nora books R7 14-16 Nov: {service.reserve(NORA, R7, nov(14, 16))}")
    print(f"Omar books R8 15-15 Nov: {service.reserve(OMAR, R8, nov(15, 15))}")
    print(f"Free rooms 12-14 Nov: {room_numbers(service.find_free_rooms(nov(12, 14)))}")
    print(f"Maya cancels R101: {service.cancel('R101')}")
    print(f"Free rooms 12-14 Nov: {room_numbers(service.find_free_rooms(nov(12, 14)))}")
    print(f"Confirmation emails sent: {email.sent}")


def run_race(service: BookingService, store: ReservationStore, stagger_seconds: float = 0.1) -> int:
    """Maya and Omar book R7 for 12-14 Nov almost at once; returns the Confirmed count for R7.

    ``service`` must be built with a slow step (``main.py`` uses 0.5 s) so that
    each request waits between its availability check and its save; Omar starts
    ``stagger_seconds`` after Maya. Because both checks happen before either
    save, both are accepted (requirement R3 is broken - known defect until P09).
    ``store`` is the store ``service`` was built with; it is only read here.
    """
    stay = nov(12, 14)
    results: dict[str, BookingResult] = {}

    def request(name: str, guest: Guest) -> None:
        results[name] = service.reserve(guest, R7, stay)

    print("Maya and Omar both book R7 for 12-14 Nov at the same moment...")
    maya = threading.Thread(target=request, args=("Maya", MAYA))
    omar = threading.Thread(target=request, args=("Omar", OMAR))
    maya.start()
    time.sleep(stagger_seconds)  # Omar clicks a moment after Maya
    omar.start()
    maya.join()
    omar.join()

    print(f"Maya: {results['Maya']}")
    print(f"Omar: {results['Omar']}")
    confirmed = store.count_confirmed(R7, stay)
    print(f"Confirmed reservations for R7 on 12-14 Nov: {confirmed}")
    if confirmed > 1:
        print("Double booking! Both requests checked before either one saved.")
    else:
        print("Only one guest has R7.")
    return confirmed
