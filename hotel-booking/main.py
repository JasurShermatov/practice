"""Entry point of the hotel booking app (version 2, P04: same behaviour, cleaner structure).

    python main.py          -> the normal demo (nine lines)
    python main.py --race   -> two guests book the same room at the same moment

This file is the *composition root*: the one place that chooses the real
store and the real sender and passes them into ``BookingService``. To send
SMS instead of email, or (P07) to keep bookings in PostgreSQL, change
``build_app`` - not ``BookingService``.
"""
from __future__ import annotations

import argparse

from hotel_booking import BookingService, EmailNotificationSender, InMemoryReservationStore
from hotel_booking.demo import HOTEL_ROOMS, run_demo, run_race

RACE_SLOW_STEP_SECONDS = 0.5  # widens the check-then-save gap so the race shows (demo only)


def build_app(
    slow_step_seconds: float = 0.0,
) -> tuple[BookingService, InMemoryReservationStore, EmailNotificationSender]:
    """Create the real objects and wire them together.

    Returns the store and the sender too, because the demo reports what they hold.
    """
    store = InMemoryReservationStore()
    email = EmailNotificationSender()
    service = BookingService(HOTEL_ROOMS, store, email, slow_step_seconds=slow_step_seconds)
    return service, store, email


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Hotel booking app, version 2 (P04).")
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
        run_demo(service, email)


if __name__ == "__main__":
    main()
