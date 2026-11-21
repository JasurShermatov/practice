"""DateRange, Reservation and the value/entity rules (R3, R4)."""
from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from hotel_booking import DateRange, Reservation, ReservationStatus
from hotel_booking.demo import MAYA, R7, R8, nov


class TestDateRange:
    def test_check_out_after_check_in_is_valid(self) -> None:
        assert nov(12, 14).is_valid()

    @pytest.mark.parametrize(("check_in", "check_out"), [(15, 15), (16, 14)])
    def test_zero_or_negative_nights_is_invalid(self, check_in: int, check_out: int) -> None:
        assert not nov(check_in, check_out).is_valid()

    @pytest.mark.parametrize(
        ("existing", "requested", "expected"),
        [
            ((12, 14), (13, 15), True),   # Omar: shares the night of the 13th
            ((12, 14), (14, 16), False),  # Nora: check-out day is free (half-open)
            ((14, 16), (12, 14), False),  # same pair, other order
            ((12, 14), (10, 12), False),  # ends on Maya's check-in day
            ((12, 14), (11, 13), True),   # shares the night of the 12th
            ((12, 16), (13, 14), True),   # fully inside
            ((13, 14), (12, 16), True),   # fully around
            ((12, 14), (12, 14), True),   # identical
        ],
        ids=["omar-13-15", "nora-14-16", "reverse-order", "ends-on-check-in",
             "night-of-12th", "inside", "around", "identical"],
    )
    def test_overlap_counts_nights_not_dates(
        self, existing: tuple[int, int], requested: tuple[int, int], expected: bool
    ) -> None:
        assert nov(*existing).overlaps(nov(*requested)) is expected
        assert nov(*requested).overlaps(nov(*existing)) is expected  # symmetric

    def test_is_a_value_equal_by_content_and_immutable(self) -> None:
        assert nov(12, 14) == DateRange(date(2026, 11, 12), date(2026, 11, 14))
        with pytest.raises(dataclasses.FrozenInstanceError):
            nov(12, 14).check_out = date(2026, 11, 20)  # type: ignore[misc]


class TestReservation:
    def test_new_reservation_is_confirmed_and_keeps_its_facts(self) -> None:
        r101 = Reservation("R101", MAYA, R7, nov(12, 14))
        assert (r101.id, r101.guest, r101.room, r101.stay, r101.status) == (
            "R101", MAYA, R7, nov(12, 14), ReservationStatus.CONFIRMED,
        )

    def test_blocks_only_same_room_and_shared_night(self) -> None:
        r101 = Reservation("R101", MAYA, R7, nov(12, 14))
        assert r101.blocks(R7, nov(13, 15))
        assert not r101.blocks(R7, nov(14, 16))
        assert not r101.blocks(R8, nov(12, 14))

    def test_cancel_once_then_again(self) -> None:
        r101 = Reservation("R101", MAYA, R7, nov(12, 14))
        assert r101.cancel() is True
        assert r101.status is ReservationStatus.CANCELLED
        assert r101.cancel() is False  # already Cancelled: nothing changes
        assert r101.status is ReservationStatus.CANCELLED

    def test_cancelled_reservation_no_longer_blocks(self) -> None:
        r101 = Reservation("R101", MAYA, R7, nov(12, 14))
        r101.cancel()
        assert not r101.blocks(R7, nov(12, 14))

    def test_status_can_only_change_through_cancel(self) -> None:
        r101 = Reservation("R101", MAYA, R7, nov(12, 14))
        with pytest.raises(AttributeError):
            r101.status = ReservationStatus.CANCELLED  # type: ignore[misc]
