"""Reservations: who has which room for which nights. Owns the booking rule (rule cards 1-3).

Public contract: the booking service and its answer, the words of the context
(Stay = ``DateRange``, ``Guest``, ``Reservation``, ``ReservationStatus``) and
the ``ReservationStore`` promise the wiring plugs a store into. The store
itself (``internal.py``) is private.

Reservations may use only the public contracts of Rooms, Payments and
Notifications (architecture rule 1).
"""
from hotel_booking.reservations.booking import BookingOutcome, BookingResult, BookingService, ReservationStore
from hotel_booking.reservations.domain import DateRange, Guest, Reservation, ReservationStatus

__all__ = [
    "BookingOutcome",
    "BookingResult",
    "BookingService",
    "DateRange",
    "Guest",
    "Reservation",
    "ReservationStatus",
    "ReservationStore",
]
