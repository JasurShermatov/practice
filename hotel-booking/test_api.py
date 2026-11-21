"""The eight API tests: HTTP in, HTTP out, with the reservations in a list and the cache in a dictionary.

The four tests of P07 Step 6, the two cache tests of P08 Step 6 and the two concurrency tests of
P09 Step 7 (the last two). Run them with the 8 booking tests from the hotel-booking folder:
python -m unittest -v   (16 tests)

Starlette's TestClient sends each request straight to the app inside the test: no server, no
network, no database. The list store is used on purpose - these tests check the HTTP answers;
the SQL store is checked in tests/test_sql_store.py and tests/test_api_sqlite.py, and every
error path in tests/test_api_http.py.

P08 change (deliberate): ``new_client`` builds the app as the P08 wiring does - one ``Stats`` shared
by GET /stats and a ``CountingReservationStore`` around the list store, and an ``AvailabilityCache``
over ``InMemoryKeyValueStore`` (the course's "cache in a dictionary"; this one even honours the TTL,
which a one-second test never reaches). The four P07 tests are unchanged. The /stats body has a
fifth counter, ``cacheErrors``, so the expected text is the course's plus ``"cacheErrors":0``.

P09 addition: ``new_app`` builds the same app but hands back the list store too and takes the slow
step, so a test can send two bookings into the gap between check and save and then count the rows.
The list store keeps the promise PostgreSQL's exclusion constraint keeps (``save`` raises
``OverlapRejected`` instead of double-booking), so these two tests need no database and still test
the rule the constraint protects. The first six tests did not change.
"""
import threading
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from starlette.testclient import TestClient

from hotel_booking.api import create_app
from hotel_booking.api_cache import AvailabilityCache, InMemoryKeyValueStore
from hotel_booking.api_stats import CountingReservationStore, Stats
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, DateRange, Guest, OverlapRejected, Reservation
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room

R7 = Room("R7", "Standard")
R8 = Room("R8", "Deluxe")
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
OMAR = {"guestName": "Omar", "guestEmail": "omar@example.com", "room": "R7", "checkIn": "2026-11-13", "checkOut": "2026-11-15"}
BOTH_FREE = ('{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},'
             '{"number":"R8","type":"Deluxe"}],"next":null}')
ONLY_R8 = '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}'


def new_client() -> TestClient:
    """The web app with the in-memory store and cache; the TestClient sends requests without a network."""
    stats = Stats()
    service = BookingService([R7, R8], CountingReservationStore(InMemoryReservationStore(), stats),
                             EmailNotificationSender())

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        yield service  # a list in memory has nothing to save at the end of a request

    return TestClient(create_app([R7, R8], unit_of_work, stats, AvailabilityCache(InMemoryKeyValueStore())))


def new_app(slow_step_seconds: float = 0.0) -> tuple[TestClient, InMemoryReservationStore]:
    """P09: the same app over one list store the test can look at afterwards, with the slow step."""
    stats = Stats()
    store = InMemoryReservationStore()
    service = BookingService([R7, R8], CountingReservationStore(store, stats), EmailNotificationSender(),
                             slow_step_seconds=slow_step_seconds)

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        yield service

    app = create_app([R7, R8], unit_of_work, stats, AvailabilityCache(InMemoryKeyValueStore()))
    return TestClient(app), store


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

    def test_the_second_search_is_answered_by_the_cache(self) -> None:
        client = new_client()
        first = client.get(SEARCH)
        second = client.get(SEARCH)
        self.assertEqual(first.text, second.text)
        self.assertEqual('{"searches":2,"databaseQueries":2,"cacheHits":1,"cacheMisses":1,"cacheErrors":0}',
                         client.get("/stats").text)

    def test_a_booking_and_a_cancel_make_the_next_search_fresh(self) -> None:
        client = new_client()
        self.assertEqual(BOTH_FREE, client.get(SEARCH).text)
        self.assertEqual(201, client.post("/reservations", json=MAYA).status_code)
        self.assertEqual(ONLY_R8, client.get(SEARCH).text)
        self.assertEqual(204, client.delete("/reservations/R101").status_code)
        self.assertEqual(BOTH_FREE, client.get(SEARCH).text)

    # ---------------------------------------------------------------- P09
    def test_two_bookings_at_the_same_moment_give_the_room_one_reservation(self) -> None:
        """Step 1's race, as a test. Both requests pass the pre-check; only one may be saved."""
        client, store = new_app(slow_step_seconds=0.3)  # wide enough that both pass the check first
        same_stay = {**OMAR, "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
        answers: dict[str, int] = {}

        maya = threading.Thread(target=lambda: answers.update(maya=client.post("/reservations", json=MAYA).status_code))
        omar = threading.Thread(target=lambda: answers.update(omar=client.post("/reservations", json=same_stay).status_code))
        maya.start()
        omar.start()
        maya.join()
        omar.join()

        self.assertEqual([201, 409], sorted(answers.values()))
        self.assertEqual(1, store.count_confirmed(R7, DateRange(date(2026, 11, 12), date(2026, 11, 14))))

    def test_the_store_refuses_an_overlapping_save_even_without_the_pre_check(self) -> None:
        """The promise the exclusion constraint keeps in PostgreSQL, kept by the list store too.
        Nothing calls has_overlap here: save itself must refuse."""
        store = InMemoryReservationStore()
        stay = DateRange(date(2026, 11, 12), date(2026, 11, 14))
        store.save(Reservation("R101", Guest("Maya", "maya@example.com"), R7, stay))

        overlapping = Reservation("R102", Guest("Omar", "omar@example.com"), R7,
                                  DateRange(date(2026, 11, 13), date(2026, 11, 15)))
        with self.assertRaises(OverlapRejected):
            store.save(overlapping)
        self.assertEqual(1, store.count_confirmed(R7, stay))


if __name__ == "__main__":
    unittest.main()
