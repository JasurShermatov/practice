"""Before/after behaviour check for P04: accepted, full and error cases, plus the saved records.

Runs one fixed scenario against a hotel-booking project folder and prints every
answer and every saved reservation. Run it once against the P03 code and once
against the P04 code and diff the two outputs: a pure refactoring prints the
same text.

    python compare_behaviour.py <path-to-hotel-booking-folder>

It works with both versions: P03 names (ReservationStore, EmailSender) and
P04 names (InMemoryReservationStore, EmailNotificationSender).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any


def build(project: Path) -> tuple[Any, Any, Any, Any]:
    sys.path.insert(0, str(project))
    import hotel_booking as hb  # the project under test

    store_cls = getattr(hb, "InMemoryReservationStore", None) or hb.ReservationStore
    sender_cls = getattr(hb, "EmailNotificationSender", None) or hb.EmailSender
    store, sender = store_cls(), sender_cls()
    rooms = [hb.Room("R7", "Standard"), hb.Room("R8", "Deluxe")]
    return hb, hb.BookingService(rooms, store, sender), store, sender


def main(project: Path) -> None:
    hb, service, store, sender = build(project)
    r7, r8 = hb.Room("R7", "Standard"), hb.Room("R8", "Deluxe")
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
    main(Path(sys.argv[1]).resolve())
