"""Hotel booking app - version 1 (P03): domain classes and the booking workflow, in memory."""
from .booking import BookingOutcome, BookingResult, BookingService
from .domain import DateRange, Guest, Reservation, ReservationStatus, Room
from .notifications import EmailSender
from .stores import ReservationStore

__all__ = [
    "BookingOutcome",
    "BookingResult",
    "BookingService",
    "DateRange",
    "EmailSender",
    "Guest",
    "Reservation",
    "ReservationStatus",
    "ReservationStore",
    "Room",
]
