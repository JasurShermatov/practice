"""Shared test fixtures: a fresh hotel with rooms R7 and R8 and an empty store."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from hotel_booking import BookingService, EmailNotificationSender, InMemoryReservationStore
from hotel_booking.demo import HOTEL_ROOMS


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
