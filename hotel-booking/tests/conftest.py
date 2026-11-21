"""Shared test fixtures: a fresh hotel with rooms R7 and R8 and an empty store.

P06 change (deliberate, imports only): the classes now come from their modules;
the tests, like the wiring, may name internal classes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from hotel_booking.demo import HOTEL_ROOMS
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore


@dataclass
class Hotel:
    service: BookingService
    store: InMemoryReservationStore
    email: EmailNotificationSender


@pytest.fixture
def hotel() -> Hotel:
    store = InMemoryReservationStore()
    email = EmailNotificationSender()
    return Hotel(BookingService(HOTEL_ROOMS, store, email), store, email)
