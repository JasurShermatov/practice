"""The four API tests of P07 Step 6: HTTP in, HTTP out, with the reservations in a list.

Run them with the 8 booking tests from the hotel-booking folder:  python -m unittest -v   (12 tests)

Starlette's TestClient sends each request straight to the app inside the test: no server, no
network, no database. The list store is used on purpose - these tests check the HTTP answers;
the SQL store is checked in tests/test_sql_store.py and tests/test_api_sqlite.py, and every
error path in tests/test_api_http.py.
"""
import unittest
from collections.abc import Iterator
from contextlib import contextmanager

from starlette.testclient import TestClient

from hotel_booking.api import create_app
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room

R7 = Room("R7", "Standard")
R8 = Room("R8", "Deluxe")
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
OMAR = {"guestName": "Omar", "guestEmail": "omar@example.com", "room": "R7", "checkIn": "2026-11-13", "checkOut": "2026-11-15"}


def new_client() -> TestClient:
    """The web app with the in-memory store, exactly as the wiring had it before the database."""
    service = BookingService([R7, R8], InMemoryReservationStore(), EmailNotificationSender())

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        yield service  # a list in memory has nothing to save at the end of a request

    return TestClient(create_app([R7, R8], unit_of_work))


class ApiTests(unittest.TestCase):
    def test_search_answers_200_with_the_free_rooms(self) -> None:
        response = new_client().get(SEARCH)
        self.assertEqual(200, response.status_code)
        self.assertEqual('{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},'
                         '{"number":"R8","type":"Deluxe"}],"next":null}', response.text)

    def test_booking_answers_201_then_409_for_a_shared_night(self) -> None:
        client = new_client()
        first = client.post("/reservations", json=MAYA)
        self.assertEqual(201, first.status_code)
        self.assertEqual('{"id":"R101","status":"Confirmed","notificationFailed":false}', first.text)
        second = client.post("/reservations", json=OMAR)
        self.assertEqual(409, second.status_code)
        self.assertEqual("Unavailable", second.json()["title"])

    def test_wrong_dates_answer_400_with_problem_details(self) -> None:
        response = new_client().post("/reservations", json={**OMAR, "room": "R8", "checkIn": "2026-11-15", "checkOut": "2026-11-15"})
        self.assertEqual(400, response.status_code)
        self.assertEqual("application/problem+json", response.headers["content-type"])
        self.assertEqual('{"title":"InvalidDates","status":400,"detail":"checkOut must be after checkIn."}', response.text)

    def test_cancel_answers_204_then_404(self) -> None:
        client = new_client()
        client.post("/reservations", json=MAYA)
        self.assertEqual(204, client.delete("/reservations/R101").status_code)
        second = client.delete("/reservations/R101")
        self.assertEqual(404, second.status_code)
        self.assertEqual("NotFound", second.json()["title"])


if __name__ == "__main__":
    unittest.main()
