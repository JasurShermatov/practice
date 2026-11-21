"""Entry point of the hotel booking app (version 3, P06: the P04 app as a modular monolith).

    python main.py          -> the normal demo (nine lines)
    python main.py --race   -> two guests book the same room at the same moment

This file is the *wiring* (composition root): the only application file that
names internal classes of the modules. It creates the room catalog, the store
and the sender, asks the catalog for the rooms and hands everything to
``BookingService``, which only knows the contracts. To send SMS instead of
email, or (P07) to keep bookings in PostgreSQL, change ``build_app`` - not
any module. Payments is not wired yet: nothing calls it before the P17 saga.
"""
from __future__ import annotations

import argparse

from hotel_booking.demo import HOTEL_ROOMS, run_demo, run_race
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms.internal import InMemoryRoomCatalog

RACE_SLOW_STEP_SECONDS = 0.5  # widens the check-then-save gap so the race shows (demo only)


def build_app(
    slow_step_seconds: float = 0.0,
) -> tuple[BookingService, InMemoryReservationStore, EmailNotificationSender]:
    """Create the real objects of every module and wire them together.

    Returns the store and the sender too, because the demo reports what they hold.
    """
    catalog = InMemoryRoomCatalog(HOTEL_ROOMS)  # Rooms: R7 Standard, R8 Deluxe
    store = InMemoryReservationStore()          # Reservations' private rows
    email = EmailNotificationSender()           # Notifications: how the guest is told
    service = BookingService(catalog.all(), store, email, slow_step_seconds=slow_step_seconds)
    return service, store, email


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Hotel booking app, version 3 (P06 modular monolith).")
    parser.add_argument(
        "--race",
        action="store_true",
        help="run two simultaneous bookings of R7 and show the double booking",
    )
    args = parser.parse_args(argv)
    if args.race:
        service, store, _ = build_app(slow_step_seconds=RACE_SLOW_STEP_SECONDS)
        run_race(service, store)
    else:
        service, _, email = build_app()
        run_demo(service, lambda: email.sent)


if __name__ == "__main__":
    main()
