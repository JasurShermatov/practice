"""Rooms: which rooms the hotel sells. Public contract: ``Room`` and ``RoomCatalog``.

Rooms depends on no other module (architecture rule 2).
"""
from hotel_booking.rooms.catalog import Room, RoomCatalog

__all__ = ["Room", "RoomCatalog"]
