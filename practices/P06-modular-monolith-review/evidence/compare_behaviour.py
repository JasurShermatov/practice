"""Before/after behaviour check for P06: accepted, full and error cases, plus the saved records.

Runs one fixed scenario against a hotel-booking project folder and prints every
answer, the confirmations sent and every saved reservation. Run it against the
P04 code (version 2, one flat package) and the P06 code (version 3, four
modules) and diff the two outputs: moving code into modules must print the
same text.

    python3 -I compare_behaviour.py <path-to-hotel-booking-folder>

It finds the classes in either shape: version 2 re-exports everything from
``hotel_booking``; version 3 exports nothing there, so the classes are taken
from the module contracts and their ``internal`` modules (as the tests and the
wiring may). (The P04 script of the same name only knows the flat shape.)
"""
from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

NAMES = ["BookingService", "DateRange", "Guest", "Room", "InMemoryReservationStore", "EmailNotificationSender"]
V3_PLACES = [
    "hotel_booking.reservations", "hotel_booking.reservations.internal", "hotel_booking.rooms",
    "hotel_booking.notifications.internal",
]


def load(project: Path) -> tuple[str, SimpleNamespace]:
    sys.path.insert(0, str(project))
    flat = importlib.import_module("hotel_booking")
    if all(hasattr(flat, name) for name in NAMES):
        return "version 2 (flat package)", SimpleNamespace(**{name: getattr(flat, name) for name in NAMES})
    found: dict[str, Any] = {}
    for place in V3_PLACES:
        module = importlib.import_module(place)
        found.update({name: getattr(module, name) for name in NAMES if hasattr(module, name)})
    return "version 3 (four modules)", SimpleNamespace(**found)


def main(project: Path) -> None:
    shape, hb = load(project)
    print(f"# shape found: {shape}", file=sys.stderr)  # stderr, so the two stdouts can be diffed
    store, sender = hb.InMemoryReservationStore(), hb.EmailNotificationSender()
    r7, r8 = hb.Room("R7", "Standard"), hb.Room("R8", "Deluxe")
    service = hb.BookingService([r7, r8], store, sender)
    maya, omar, nora = (hb.Guest(n, f"{n.lower()}@example.com") for n in ("Maya", "Omar", "Nora"))

    def nov(a: int, b: int) -> Any:
        return hb.DateRange(date(2026, 11, a), date(2026, 11, b))

    def free(a: int, b: int) -> str:
        return ", ".join(room.number for room in service.find_free_rooms(nov(a, b))) or "(none - full)"

    steps = [
        ("accepted", "Maya R7 12-14", lambda: service.reserve(maya, r7, nov(12, 14))),
        ("full", "Omar R7 13-15", lambda: service.reserve(omar, r7, nov(13, 15))),
        ("accepted", "Nora R7 14-16 (adjacent)", lambda: service.reserve(nora, r7, nov(14, 16))),
        ("error", "Omar R8 15-15 (zero nights)", lambda: service.reserve(omar, r8, nov(15, 15))),
        ("error", "Omar R8 16-14 (reversed)", lambda: service.reserve(omar, r8, nov(16, 14))),
        ("accepted", "Omar R8 12-14", lambda: service.reserve(omar, r8, nov(12, 14))),
        ("search", "free 12-14", lambda: free(12, 14)),
        ("full", "Nora R8 13-14", lambda: service.reserve(nora, r8, nov(13, 14))),
        ("cancel", "cancel R101", lambda: service.cancel("R101")),
        ("cancel", "cancel R101 again", lambda: service.cancel("R101")),
        ("cancel", "cancel R999 (unknown)", lambda: service.cancel("R999")),
        ("search", "free 12-14", lambda: free(12, 14)),
    ]
    for kind, label, action in steps:
        print(f"{kind:8} {label:28} -> {action()}")

    print(f"confirmations sent: {sender.sent}")
    print(f"saved records: {store.count()}")
    for number in range(101, 101 + store.count()):
        row = store.find(f"R{number}")
        print(
            f"  {row.id} {row.guest.name} {row.room.number} "
            f"{row.stay.check_in.isoformat()}..{row.stay.check_out.isoformat()} {row.status.value}"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]).resolve())
