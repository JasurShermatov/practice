"""The web app as main.py wires it: HTTP API + SQL store + unit of work, on a SQLite file (P07 Step 8).

- docs/api-check.md, automated: the seven requests and their exact answers, then the restart
  check (a second app over the same file still sees Maya's booking), then the rows in the table.
- The unit of work: a request that fails half-way leaves no row behind.
- The race through the real wiring (KNOWN DEFECT until P09, pinned here): the database alone
  does not stop a double booking; when both requests number their booking R101, the primary key
  refuses the second (500) - one booking, but not the 409 the guest should get.
- ``python main.py`` without a flag starts the web app (P07 change), ``--demo`` the demo.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import main
from hotel_booking.demo import R7, nov
from hotel_booking.notifications import Confirmation
from hotel_booking.reservations.internal import SqlReservationStore

PROJECT = Path(__file__).resolve().parents[1]
REQUESTS = PROJECT / "docs" / "requests"
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"


def body(name: str) -> dict[str, str]:
    return json.loads((REQUESTS / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def client_over(path: Path, slow_step_seconds: float = 0.0) -> TestClient:
    app, _ = main.build_api(main.sqlite_connector(path), slow_step_seconds)
    return TestClient(app, raise_server_exceptions=False)


def answer(response: object) -> tuple[int, str]:
    return response.status_code, response.text  # type: ignore[attr-defined]


def test_api_check_seven_requests_then_the_restart(tmp_path: Path) -> None:
    database = tmp_path / "hotel.sqlite3"
    client = client_over(database)
    assert answer(client.get(SEARCH)) == (200, '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},{"number":"R8","type":"Deluxe"}],"next":null}')
    assert answer(client.post("/reservations", json=body("maya-r7.json"))) == (201, '{"id":"R101","status":"Confirmed","notificationFailed":false}')
    assert answer(client.post("/reservations", json=body("omar-r7.json"))) == (409, '{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}')
    assert answer(client.post("/reservations", json=body("omar-r8.json"))) == (400, '{"title":"InvalidDates","status":400,"detail":"checkOut must be after checkIn."}')
    assert answer(client.get(SEARCH)) == (200, '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}')
    assert answer(client.delete("/reservations/R101")) == (204, "")
    assert answer(client.delete("/reservations/R101")) == (404, '{"title":"NotFound","status":404,"detail":"There is no confirmed reservation R101."}')

    # Restart check: book again, throw the app away, start a new one over the same file.
    assert answer(client.post("/reservations", json=body("maya-r7.json"))) == (201, '{"id":"R102","status":"Confirmed","notificationFailed":false}')
    del client
    restarted = client_over(database)
    assert answer(restarted.get(SEARCH)) == (200, '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R8","type":"Deluxe"}],"next":null}')

    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute("SELECT id, guest_name, room, check_in, check_out, status FROM reservations ORDER BY id").fetchall()
    assert rows == [("R101", "Maya", "R7", "2026-11-12", "2026-11-14", "Cancelled"),
                    ("R102", "Maya", "R7", "2026-11-12", "2026-11-14", "Confirmed")]


def test_the_extra_request_files_give_the_other_error_titles(tmp_path: Path) -> None:
    client = client_over(tmp_path / "hotel.sqlite3")
    titles = {name: client.post("/reservations", json=body(name)).json()["title"]
              for name in ("nora-r99.json", "maya-no-email.json", "maya-bad-date.json")}
    assert titles == {"nora-r99.json": "UnknownRoom", "maya-no-email.json": "InvalidRequest",
                      "maya-bad-date.json": "InvalidDates"}


def test_a_list_store_app_forgets_on_restart_the_database_app_does_not(tmp_path: Path) -> None:
    """L04's point, side by side: state inside the app is lost with the app; state in the database is not."""
    database = tmp_path / "hotel.sqlite3"
    client_over(database).post("/reservations", json=body("maya-r7.json"))
    assert [room["number"] for room in client_over(database).get(SEARCH).json()["rooms"]] == ["R8"]

    from test_api import new_client  # the list-store app of the course's API tests

    new_client().post("/reservations", json=body("maya-r7.json"))
    assert [room["number"] for room in new_client().get(SEARCH).json()["rooms"]] == ["R7", "R8"]


def test_a_request_that_fails_half_way_leaves_nothing_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The INSERT happened, then the request failed before commit: the unit of work rolls back."""
    database = tmp_path / "hotel.sqlite3"
    client = client_over(database)

    def broken_commit(self: SqlReservationStore) -> int:
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(SqlReservationStore, "save_changes", broken_commit)
    response = client.post("/reservations", json=body("maya-r7.json"))
    assert response.status_code == 500 and response.json()["title"] == "InternalError"
    monkeypatch.undo()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT count(*) FROM reservations").fetchone() == (0,)
    assert client.post("/reservations", json=body("maya-r7.json")).json()["id"] == "R101"


def race(client: TestClient, omar_after: float) -> dict[str, tuple[int, str]]:
    """Maya and Omar book R7 for 12-14 Nov through HTTP; Omar starts ``omar_after`` s later."""
    answers: dict[str, tuple[int, str]] = {}
    omar_body = {**body("omar-r7.json"), "checkIn": "2026-11-12", "checkOut": "2026-11-14"}

    def book(name: str, guest_body: dict[str, str]) -> None:
        response = client.post("/reservations", json=guest_body)
        answers[name] = (response.status_code, response.json()["title" if response.status_code >= 400 else "id"])

    maya = threading.Thread(target=book, args=("Maya", body("maya-r7.json")))
    omar = threading.Thread(target=book, args=("Omar", omar_body))
    maya.start()
    time.sleep(omar_after)
    omar.start()
    maya.join()
    omar.join()
    return answers


def confirmed_r7(database: Path) -> int:
    with closing(main.sqlite_connector(database)()) as connection:
        return SqlReservationStore(connection, [R7]).count_confirmed(R7, nov(12, 14))


def test_race_through_the_database_still_double_books_known_defect(tmp_path: Path) -> None:
    """KNOWN DEFECT (S2/R3), kept on purpose until P09 - the P03 race, now over HTTP and SQL.

    The database alone does not stop it: both requests check before either one saves (the slow
    step), then each numbers its booking after the other has committed - R101 and R102 - and both
    INSERTs are fine. Two Confirmed reservations for R7 on the same nights. P09 must make Omar's
    answer 409 Unavailable and this count 1.
    """
    database = tmp_path / "hotel.sqlite3"
    answers = race(client_over(database, slow_step_seconds=0.3), omar_after=0.05)
    assert answers == {"Maya": (201, "R101"), "Omar": (201, "R102")}
    assert confirmed_r7(database) == 2


class SlowSender:
    """Sends the confirmation slowly, i.e. inside Maya's open transaction (after INSERT, before COMMIT)."""

    def send_confirmation(self, confirmation: Confirmation) -> None:
        time.sleep(0.3)


def test_two_requests_numbering_r101_the_primary_key_refuses_the_second(tmp_path: Path) -> None:
    """The activity sheet's "a second R101 is refused", over HTTP (KNOWN DEFECT until P09).

    Maya's INSERT of R101 is not committed yet while her confirmation is sent. Omar checks and
    counts in that window: he sees no committed row, so he is free and his id is R101 too. His
    INSERT waits for Maya's write lock and is then refused by the primary key: 500 InternalError,
    his transaction is rolled back. One booking, but an ugly answer - P09 turns it into 409.
    """
    database = tmp_path / "hotel.sqlite3"
    app, _ = main.build_api(main.sqlite_connector(database), sender=SlowSender())
    answers = race(TestClient(app, raise_server_exceptions=False), omar_after=0.1)
    assert answers == {"Maya": (201, "R101"), "Omar": (500, "InternalError")}
    assert confirmed_r7(database) == 1


def test_main_without_a_flag_starts_the_web_app(capsys: pytest.CaptureFixture[str]) -> None:
    started: list[tuple[str, int]] = []
    main.main([], serve=lambda database, port: started.append((database, port)))
    assert started == [("sqlite", 5080)]
    assert capsys.readouterr().out == ""


def test_main_db_and_port_options_reach_the_server() -> None:
    started: list[tuple[str, int]] = []
    main.main(["--db", "postgres", "--port", "5081"], serve=lambda database, port: started.append((database, port)))
    assert started == [("postgres", 5081)]
