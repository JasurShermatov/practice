"""The Rooms contract: what a room is, and the promise "tell me which rooms the hotel sells"."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Room:
    """A room the hotel sells. ``type`` is a label ("Standard", "Deluxe"), not a subclass.

    Moved unchanged from ``domain.py`` (P03/P04). Rooms owns rule cards 4 and 5
    (out of service, nightly price); when they arrive they are added here, not
    in Reservations.
    """

    number: str
    type: str


class RoomCatalog(Protocol):
    """Rooms' public promise: which rooms the hotel sells. A list today; a table from P07."""

    def all(self) -> list[Room]:
        """Every room on sale, in a stable order (R7 before R8)."""
        ...
