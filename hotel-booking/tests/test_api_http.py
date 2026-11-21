"""The HTTP API, success and every error path (P07 Steps 5-6, beyond the course's four tests).

Uses the list store, like the course's API tests, through Starlette's TestClient (no server, no
network). A counting unit of work shows the endpoint rule "check first, then call BookingService
once": a request refused at the edge never opens a unit of work.

Every expected body here is the exact text the contract (docs/openapi.yaml) promises; the
contract itself is checked against the app in test_openapi_contract.py.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest
from starlette.testclient import TestClient

from hotel_booking.api import DEFAULT_CONTRACT, create_app
from hotel_booking.demo import HOTEL_ROOMS, R7, nov
from hotel_booking.notifications import Confirmation
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room

SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
MAYA = {"guestName": "Maya", "guestEmail": "maya@example.com", "room": "R7", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
PROBLEM = "application/problem+json"
BODY_DETAIL = "The body must be JSON with guestName, guestEmail, room, checkIn and checkOut."
DATE_DETAIL = "checkIn and checkOut must be dates such as 2026-11-12."


class FailingSender:
    """A Notifications stand-in whose mail server is down (R6 through HTTP)."""

    def send_confirmation(self, confirmation: Confirmation) -> None:
        raise RuntimeError("The mail server is down.")


@dataclass
class Api:
    client: TestClient
    store: InMemoryReservationStore
    units_of_work: list[str] = field(default_factory=list)  # one entry per request that reached BookingService


def make_api(rooms: tuple[Room, ...] = HOTEL_ROOMS, sender: object | None = None, broken: bool = False) -> Api:
    store = InMemoryReservationStore()
    service = BookingService(rooms, store, sender or EmailNotificationSender())  # type: ignore[arg-type]
    api = Api(TestClient(create_app(rooms, lambda: unit_of_work()), raise_server_exceptions=False), store)

    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        api.units_of_work.append("opened")
        if broken:
            raise RuntimeError("the database is down")
        yield service

    return api


@pytest.fixture
def api() -> Api:
    return make_api()


def problem(status: int, title: str, detail: str) -> dict[str, object]:
    return {"title": title, "status": status, "detail": detail}


def assert_problem(response: object, status: int, title: str, detail: str) -> None:
    assert response.status_code == status  # type: ignore[attr-defined]
    assert response.headers["content-type"] == PROBLEM  # type: ignore[attr-defined]
    assert response.json() == problem(status, title, detail)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- GET /rooms/availability


def test_search_success_body_is_exact_json(api: Api) -> None:
    response = api.client.get(SEARCH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"checkIn": "2026-11-12", "checkOut": "2026-11-14",
                               "rooms": [{"number": "R7", "type": "Standard"}, {"number": "R8", "type": "Deluxe"}],
                               "next": None}
    assert api.units_of_work == ["opened"]


@pytest.mark.parametrize("query", [
    "", "checkIn=2026-11-12", "checkOut=2026-11-14",                     # missing
    "checkIn=12.11.2026&checkOut=2026-11-14", "checkIn=2026-11-12&checkOut=20261114",  # not YYYY-MM-DD
    "checkIn=2026-02-30&checkOut=2026-03-02",                              # not a real day
    "checkIn=&checkOut=2026-11-14", "checkIn=2026-1-12&checkOut=2026-11-14",
])
def test_search_without_two_real_dates_is_invalid_dates(api: Api, query: str) -> None:
    assert_problem(api.client.get(f"/rooms/availability?{query}"), 400, "InvalidDates", DATE_DETAIL)
    assert api.units_of_work == []


@pytest.mark.parametrize("check_out", ["2026-11-12", "2026-11-11"])
def test_search_with_check_out_not_after_check_in_is_invalid_dates(api: Api, check_out: str) -> None:
    response = api.client.get(f"/rooms/availability?checkIn=2026-11-12&checkOut={check_out}")
    assert_problem(response, 400, "InvalidDates", "checkOut must be after checkIn.")
    assert api.units_of_work == []


@pytest.mark.parametrize("limit", ["0", "101", "abc", "-1", "1.5", "", "1000"])
def test_search_limit_outside_1_to_100_is_invalid_request(api: Api, limit: str) -> None:
    response = api.client.get(f"{SEARCH}&limit={limit}")
    assert_problem(response, 400, "InvalidRequest", "limit must be a whole number from 1 to 100.")
    assert api.units_of_work == []


@pytest.mark.parametrize("limit", ["1", "100", "020"])
def test_search_limit_edges_are_accepted(api: Api, limit: str) -> None:
    assert api.client.get(f"{SEARCH}&limit={limit}").status_code == 200


def test_search_pages_follow_text_order_and_the_cursor() -> None:
    """The contract's three decisions: text order (R10 before R7), limit, and after = next."""
    rooms = tuple(Room(number, "Standard") for number in ("R7", "R10", "R8", "R9"))
    client = make_api(rooms).client
    pages: list[list[str]] = []
    after = ""
    while True:
        body = client.get(f"{SEARCH}&limit=3&after={after}").json()
        pages.append([room["number"] for room in body["rooms"]])
        if body["next"] is None:
            break
        after = body["next"]
    assert pages == [["R10", "R7", "R8"], ["R9"]]


def test_search_limit_1_gives_one_room_and_next(api: Api) -> None:
    """Activity sheet Step 5, item 6: &limit=1 gives one room and "next":"R7"."""
    first = api.client.get(f"{SEARCH}&limit=1").json()
    assert first["rooms"] == [{"number": "R7", "type": "Standard"}] and first["next"] == "R7"
    second = api.client.get(f"{SEARCH}&limit=1&after=R7").json()
    assert second["rooms"] == [{"number": "R8", "type": "Deluxe"}] and second["next"] is None


def test_search_after_the_last_room_is_an_empty_last_page(api: Api) -> None:
    assert api.client.get(f"{SEARCH}&after=R8").json()["rooms"] == []


def test_search_ignores_unknown_query_parameters(api: Api) -> None:
    assert api.client.get(f"{SEARCH}&utm_source=mail").status_code == 200


# --------------------------------------------------------------------------- POST /reservations


def test_booking_success_then_the_room_is_no_longer_free(api: Api) -> None:
    created = api.client.post("/reservations", json=MAYA)
    assert created.status_code == 201
    assert created.headers["content-type"] == "application/json"
    assert created.text == '{"id":"R101","status":"Confirmed","notificationFailed":false}'
    assert [room["number"] for room in api.client.get(SEARCH).json()["rooms"]] == ["R8"]


def test_booking_with_failed_confirmation_is_still_201_and_says_so() -> None:
    """R6 through HTTP: the booking is saved; notificationFailed tells the client the email did not go."""
    api = make_api(sender=FailingSender())
    response = api.client.post("/reservations", json=MAYA)
    assert response.status_code == 201
    assert response.json() == {"id": "R101", "status": "Confirmed", "notificationFailed": True}
    assert api.store.count() == 1


def test_booking_a_shared_night_is_409_unavailable(api: Api) -> None:
    api.client.post("/reservations", json=MAYA)
    response = api.client.post("/reservations", json={**MAYA, "guestName": "Omar", "checkIn": "2026-11-13", "checkOut": "2026-11-15"})
    assert_problem(response, 409, "Unavailable", "The room is booked for at least one night of this stay.")
    assert api.store.count() == 1


def test_arriving_on_the_check_out_day_is_201(api: Api) -> None:
    api.client.post("/reservations", json=MAYA)
    response = api.client.post("/reservations", json={**MAYA, "guestName": "Nora", "checkIn": "2026-11-14", "checkOut": "2026-11-16"})
    assert response.status_code == 201 and response.json()["id"] == "R102"


@pytest.mark.parametrize(("content", "content_type"), [
    (json.dumps(MAYA), "text/plain"),                      # JSON, but not sent as JSON
    (json.dumps(MAYA), None),                              # no content type at all
    ("{not json", "application/json"),
    (b"\xff\xfe", "application/json"),                     # not even UTF-8
    ("", "application/json"),                              # no body
    ("[1, 2]", "application/json"),                        # JSON, not an object
    ('"Maya"', "application/json"),
    ("null", "application/json"),
], ids=["text-plain", "no-content-type", "broken-json", "not-utf8", "empty", "array", "string", "null"])
def test_booking_body_that_is_not_a_json_object_is_invalid_request(
    api: Api, content: str | bytes, content_type: str | None
) -> None:
    headers = {"content-type": content_type} if content_type else {}
    response = api.client.post("/reservations", content=content, headers=headers)
    assert_problem(response, 400, "InvalidRequest", BODY_DETAIL)
    assert api.units_of_work == []


@pytest.mark.parametrize("field_name", ["guestName", "guestEmail", "room", "checkIn", "checkOut"])
@pytest.mark.parametrize("value", ["<missing>", "", 7, None, ["R7"], True], ids=["missing", "empty", "number", "null", "list", "bool"])
def test_booking_field_missing_empty_or_not_text_is_invalid_request(api: Api, field_name: str, value: object) -> None:
    body = {key: item for key, item in MAYA.items() if key != field_name}
    if value != "<missing>":
        body[field_name] = value  # type: ignore[assignment]
    assert_problem(api.client.post("/reservations", json=body), 400, "InvalidRequest", BODY_DETAIL)
    assert api.units_of_work == []


def test_booking_accepts_a_charset_and_ignores_unknown_fields(api: Api) -> None:
    """Tolerant reader: a newer client may send more; never break it for that."""
    body = json.dumps({**MAYA, "comment": "late arrival", "children": 1})
    response = api.client.post("/reservations", content=body, headers={"content-type": "application/json; charset=utf-8"})
    assert response.status_code == 201


def test_booking_snake_case_field_names_are_not_the_contract(api: Api) -> None:
    body = {"guest_name": "Maya", "guest_email": "maya@example.com", "room": "R7", "check_in": "2026-11-12", "check_out": "2026-11-14"}
    assert_problem(api.client.post("/reservations", json=body), 400, "InvalidRequest", BODY_DETAIL)


@pytest.mark.parametrize(("check_in", "check_out"), [
    ("12.11.2026", "14.11.2026"), ("2026-11-12", "tomorrow"), ("2026-13-01", "2026-13-03"), ("20261112", "20261114"),
])
def test_booking_dates_that_are_not_real_dates_are_invalid_dates(api: Api, check_in: str, check_out: str) -> None:
    response = api.client.post("/reservations", json={**MAYA, "checkIn": check_in, "checkOut": check_out})
    assert_problem(response, 400, "InvalidDates", DATE_DETAIL)
    assert api.units_of_work == []


@pytest.mark.parametrize("check_out", ["2026-11-12", "2026-11-10"])
def test_booking_without_a_night_is_invalid_dates_decided_by_booking_service(api: Api, check_out: str) -> None:
    """The order of the dates is the booking rule's job, so this request does reach BookingService."""
    response = api.client.post("/reservations", json={**MAYA, "checkOut": check_out})
    assert_problem(response, 400, "InvalidDates", "checkOut must be after checkIn.")
    assert api.units_of_work == ["opened"]
    assert api.store.count() == 0


def test_booking_an_unknown_room_is_400_unknown_room(api: Api) -> None:
    response = api.client.post("/reservations", json={**MAYA, "room": "R99"})
    assert_problem(response, 400, "UnknownRoom", "There is no room R99.")
    assert api.units_of_work == []


def test_booking_room_numbers_are_exact_text(api: Api) -> None:
    assert api.client.post("/reservations", json={**MAYA, "room": "r7"}).json()["title"] == "UnknownRoom"


# --------------------------------------------------------------------------- DELETE /reservations/{id}


def test_cancel_unknown_id_is_404_not_found(api: Api) -> None:
    assert_problem(api.client.delete("/reservations/R404"), 404, "NotFound", "There is no confirmed reservation R404.")


def test_cancel_frees_the_room_and_keeps_the_reservation_as_history(api: Api) -> None:
    api.client.post("/reservations", json=MAYA)
    response = api.client.delete("/reservations/R101")
    assert response.status_code == 204 and response.content == b""
    assert [room["number"] for room in api.client.get(SEARCH).json()["rooms"]] == ["R7", "R8"]
    assert api.store.count() == 1  # Cancelled, not deleted: the next id is still R102
    assert api.client.post("/reservations", json=MAYA).json()["id"] == "R102"


def test_cancel_id_with_sql_like_text_is_just_an_unknown_id(api: Api) -> None:
    assert api.client.delete("/reservations/R101' OR '1'='1").status_code == 404


# --------------------------------------------------------------------------- repeating a request (idempotency)


def test_delete_is_idempotent_the_repeat_answers_404_and_changes_nothing(api: Api) -> None:
    api.client.post("/reservations", json=MAYA)
    answers = [api.client.delete("/reservations/R101").status_code for _ in range(3)]
    assert answers == [204, 404, 404]
    assert api.store.count() == 1 and api.store.count_confirmed(R7, nov(12, 14)) == 0


def test_get_is_safe_repeating_it_changes_nothing(api: Api) -> None:
    first = api.client.get(SEARCH).text
    assert [api.client.get(SEARCH).text for _ in range(3)] == [first] * 3
    assert api.store.count() == 0


def test_post_is_not_idempotent_a_retry_answers_409_for_the_guests_own_stay(api: Api) -> None:
    """KNOWN GAP, pinned on purpose until P11 (Idempotency-Key).

    Maya's phone sends the booking, loses the answer and sends the same body again. The overlap
    rule stops a second reservation, so nothing is double-booked - but the retry answers 409 and
    Maya never learns her id R101. P11 must flip this to "the same 201 R101 again".
    """
    first = api.client.post("/reservations", json=MAYA)
    retry = api.client.post("/reservations", json=MAYA)
    assert (first.status_code, retry.status_code) == (201, 409)
    assert api.store.count() == 1


# --------------------------------------------------------------------------- answers from any path


def test_unknown_path_is_404_problem_details(api: Api) -> None:
    assert_problem(api.client.get("/bookings"), 404, "NotFound", "There is no resource at /bookings.")


@pytest.mark.parametrize(("method", "path", "allow"), [
    ("PUT", "/reservations", "POST"),
    ("GET", "/reservations", "POST"),
    ("GET", "/reservations/R101", "DELETE"),
    ("POST", "/rooms/availability", "GET, HEAD"),
    ("DELETE", "/openapi.yaml", "GET, HEAD"),
])
def test_wrong_method_is_405_problem_details_with_allow(api: Api, method: str, path: str, allow: str) -> None:
    response = api.client.request(method, path)
    assert_problem(response, 405, "MethodNotAllowed", f"{method} is not allowed on {path}.")
    # Starlette keeps a route's methods in a set, so the order inside Allow is not fixed.
    assert set(response.headers["allow"].split(", ")) == set(allow.split(", "))


def test_a_failure_behind_the_api_is_500_problem_details_without_internals() -> None:
    api = make_api(broken=True)
    response = api.client.post("/reservations", json=MAYA)
    assert_problem(response, 500, "InternalError", "The server could not complete the request. Try again later.")
    assert "database" not in response.text


def test_the_contract_is_served_from_the_file(api: Api) -> None:
    response = api.client.get("/openapi.yaml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert response.text == DEFAULT_CONTRACT.read_text(encoding="utf-8")


def test_head_on_a_get_route_has_headers_and_no_body(api: Api) -> None:
    response = api.client.head(SEARCH)
    assert response.status_code == 200 and response.content == b""
