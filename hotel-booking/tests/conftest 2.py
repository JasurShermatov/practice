"""Shared test fixtures: a fresh hotel with rooms R7 and R8 and an empty store."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from hotel_booking import BookingService, EmailSender, ReservationStore
from hotel_booking.demo import HOTEL_ROOMS


@dataclass
class Hotel:
    service: BookingService
    store: ReservationStore
    email: EmailSender


@pytest.fixture
def hotel() -> Hotel:
    store = ReservationStore()
    email = EmailSender()
    return Hotel(BookingService(HOTEL_ROOMS, store, email), store, email)
