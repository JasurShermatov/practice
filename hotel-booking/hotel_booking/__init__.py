"""Hotel booking app - version 2 (P04): the P03 app with its storage and messaging behind protocols.

Version 1 (P03) built the domain classes and the booking workflow, in memory.
Version 2 keeps that behaviour and lets BookingService depend only on the
``ReservationStore`` and ``NotificationSender`` promises; ``main.py`` wires the
real classes. New behaviour: R6 (a failed confirmation keeps the booking) and an
SMS sender.
"""
from .booking import BookingOutcome, BookingResult, BookingService
from .domain import DateRange, Guest, Reservation, ReservationStatus, Room
from .notifications import EmailNotificationSender, NotificationSender, SmsNotificationSender
from .stores import InMemoryReservationStore, ReservationStore

__all__ = [
    "BookingOutcome",
    "BookingResult",
    "BookingService",
    "DateRange",
    "EmailNotificationSender",
    "Guest",
    "InMemoryReservationStore",
    "NotificationSender",
    "Reservation",
    "ReservationStatus",
    "ReservationStore",
    "Room",
    "SmsNotificationSender",
]
