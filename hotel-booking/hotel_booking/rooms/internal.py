"""Rooms' internal code: how the catalog keeps its promise. Only Rooms, the wiring and tests import this."""
from __future__ import annotations

from collections.abc import Iterable

from hotel_booking.rooms.catalog import Room


class InMemoryRoomCatalog:
    """Keeps the hotel's rooms in a list; keeps the ``RoomCatalog`` promise by shape."""

    def __init__(self, rooms: Iterable[Room]) -> None:
        self._rooms = list(rooms)

    def all(self) -> list[Room]:
        # A copy: a caller that edits the list it got must not change the catalog.
        return list(self._rooms)
