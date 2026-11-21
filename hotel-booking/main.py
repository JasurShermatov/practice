"""Entry point of the hotel booking app (version 1, in memory).

    python main.py          -> the normal demo (nine lines)
    python main.py --race   -> two guests book the same room at the same moment
"""
from __future__ import annotations

import argparse

from hotel_booking.demo import run_demo, run_race


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Hotel booking app, version 1 (P03).")
    parser.add_argument(
        "--race",
        action="store_true",
        help="run two simultaneous bookings of R7 and show the double booking",
    )
    args = parser.parse_args(argv)
    if args.race:
        run_race()
    else:
        run_demo()


if __name__ == "__main__":
    main()
