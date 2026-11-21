"""BookingService against requirements R1-R5 (one request at a time)."""
from __future__ import annotations

from hotel_booking import BookingOutcome, ReservationStatus
from hotel_booking.demo import MAYA, NORA, OMAR, R7, R8, nov

from .conftest import Hotel


def test_r1_search_empty_hotel_lists_every_room(hotel: Hotel) -> None:
    assert hotel.service.find_free_rooms(nov(12, 14)) == [R7, R8]


def test_r1_search_hides_room_with_shared_night(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    assert hotel.service.find_free_rooms(nov(12, 14)) == [R8]
    assert hotel.service.find_free_rooms(nov(14, 16)) == [R7, R8]  # check-out day is free


def test_r2_book_free_room_returns_accepted_with_id(hotel: Hotel) -> None:
    result = hotel.service.reserve(MAYA, R7, nov(12, 14))
    assert result.outcome is BookingOutcome.ACCEPTED
    assert str(result) == "Accepted R101"


def test_r2_accepted_booking_is_saved_confirmed_and_emailed(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    saved = hotel.store.find("R101")
    assert saved is not None
    assert (saved.guest, saved.room, saved.stay, saved.status) == (
        MAYA, R7, nov(12, 14), ReservationStatus.CONFIRMED,
    )
    assert hotel.email.sent == 1


def test_r2_ids_are_numbered_from_r101(hotel: Hotel) -> None:
    assert str(hotel.service.reserve(MAYA, R7, nov(12, 14))) == "Accepted R101"
    assert str(hotel.service.reserve(NORA, R7, nov(14, 16))) == "Accepted R102"


def test_r3_clash_is_unavailable_and_saves_nothing(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    result = hotel.service.reserve(OMAR, R7, nov(13, 15))
    assert str(result) == "Unavailable"
    assert hotel.store.count() == 1
    assert hotel.email.sent == 1  # no email for a refused request


def test_r3_check_out_day_is_free_for_the_next_guest(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    assert str(hotel.service.reserve(NORA, R7, nov(14, 16))) == "Accepted R102"


def test_r3_invalid_dates_save_nothing(hotel: Hotel) -> None:
    result = hotel.service.reserve(OMAR, R8, nov(15, 15))
    assert str(result) == "InvalidDates"
    assert hotel.store.count() == 0
    assert hotel.email.sent == 0


def test_r3_own_examples_for_r8_booked_20_to_22(hotel: Hotel) -> None:
    hotel.service.reserve(NORA, R8, nov(20, 22))
    assert str(hotel.service.reserve(MAYA, R8, nov(22, 24))) == "Accepted R102"
    assert str(hotel.service.reserve(OMAR, R8, nov(21, 23))) == "Unavailable"  # night of the 21st


def test_r3_invariant_at_most_one_confirmed_per_room_night(hotel: Hotel) -> None:
    """Sequential requests only: the concurrent case is in test_race.py."""
    for guest, stay in [(MAYA, nov(12, 14)), (OMAR, nov(13, 15)), (NORA, nov(11, 13)), (OMAR, nov(12, 13))]:
        hotel.service.reserve(guest, R7, stay)
    for night in range(10, 17):
        assert hotel.store.count_confirmed(R7, nov(night, night + 1)) <= 1


def test_r4_cancel_frees_the_room_and_keeps_history(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    assert hotel.service.cancel("R101") is True
    assert hotel.service.find_free_rooms(nov(12, 14)) == [R7, R8]
    kept = hotel.store.find("R101")
    assert kept is not None and kept.status is ReservationStatus.CANCELLED
    assert hotel.store.count() == 1  # nothing deleted


def test_r4_cancel_twice_or_unknown_id_returns_false(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    hotel.service.cancel("R101")
    assert hotel.service.cancel("R101") is False
    assert hotel.service.cancel("R999") is False


def test_r4_new_booking_after_cancel_gets_a_new_id(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    hotel.service.cancel("R101")
    assert str(hotel.service.reserve(OMAR, R7, nov(13, 15))) == "Accepted R102"


def test_r5_view_booking_by_id(hotel: Hotel) -> None:
    hotel.service.reserve(MAYA, R7, nov(12, 14))
    r101 = hotel.store.find("R101")
    assert r101 is not None
    assert (r101.guest.name, r101.room.number, r101.stay, r101.status.value) == (
        "Maya", "R7", nov(12, 14), "Confirmed",
    )
    assert hotel.store.find("R404") is None
