"""The web app as main.py wires it: HTTP API + SQL store + unit of work, on a SQLite file (P07 Step 8).

- docs/api-check.md, automated: the seven requests and their exact answers, then the restart
  check (a second app over the same file still sees Maya's booking), then the rows in the table.
- The unit of work: a request that fails half-way leaves no row behind.
- The race through the real wiring - a KNOWN DEFECT pinned here in P07/P08 (two Confirmed rows,
  or a 500 when both requests numbered their booking R101), a REGRESSION TEST since P09: exactly
  one booking wins, the other gets 409 Unavailable, the table holds one Confirmed row.
- ``python main.py`` without a flag starts the web app (P07 change), ``--demo`` the demo.

P09 change (deliberate): the two known-defect tests became regression tests that assert the correct
behaviour (their old assertions were the defect). ``test_race_through_the_database_still_double_books_known_defect``
-> ``test_race_through_the_database_gives_the_room_to_one_guest``: same race, same timing, now
Maya 201 R101 / Omar 409 Unavailable and one Confirmed row. ``test_two_requests_numbering_r101_the_primary_key_refuses_the_second``
-> ``test_a_booking_made_while_another_is_uncommitted_gets_its_own_id_and_a_409``: same slow
sender, now Omar's id comes from the database's counter (no second R101, so no 500) and the
no-overlap trigger refuses his row (409). New: the slow step and the port reach the server from
HOTEL_SLOW_STEP / HOTEL_PORT; a version-5 file is upgraded, or refused while it holds a double booking.

P08 change (deliberate): ``main(serve=...)`` now hands the server one ``ServerOptions`` value
(database, port, cache, invalidation) instead of ``(database, port)``, because the cache options
joined. The two command-line tests compare that value; the defaults are the course's (SQLite here,
port 5080, Redis, invalidation on). ``client_over`` keeps building the app without a cache, so every
P07 check here runs exactly as before (the cache through the wiring: tests/test_cache_wiring.py).
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


def test_race_through_the_database_gives_the_room_to_one_guest(tmp_path: Path) -> None:
    """REGRESSION (S2/R3, fixed in P09) - the P03 race over HTTP and SQL; until P08 it double-booked.

    Both requests still pass the pre-check before either saves (the slow step). Maya's INSERT goes
    in; Omar's is refused by the database (trigger reservations_no_overlap_insert), the store
    raises OverlapRejected, BookingService answers Unavailable, the API 409. Omar drew R102 before
    he was refused; a refused number is not handed out again (like a PostgreSQL sequence).
    """
    database = tmp_path / "hotel.sqlite3"
    answers = race(client_over(database, slow_step_seconds=0.3), omar_after=0.05)
    assert answers == {"Maya": (201, "R101"), "Omar": (409, "Unavailable")}
    assert confirmed_r7(database) == 1
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT id, guest_name, status FROM reservations").fetchall() == [
            ("R101", "Maya", "Confirmed")]
        assert connection.execute("SELECT last_value FROM reservation_ids").fetchone() == (102,)


class SlowSender:
    """Sends the confirmation slowly, i.e. inside Maya's open transaction (after INSERT, before COMMIT)."""

    def send_confirmation(self, confirmation: Confirmation) -> None:
        time.sleep(0.3)


def test_a_booking_made_while_another_is_uncommitted_gets_its_own_id_and_a_409(tmp_path: Path) -> None:
    """REGRESSION (fixed in P09) - until P08 this was "two requests numbering R101": 500 InternalError.

    Maya's INSERT of R101 is not committed yet while her confirmation is sent. Omar checks in that
    window and sees no committed row, so he passes the pre-check. His id no longer comes from
    counting rows (he would get R101 again): the store's UPDATE of reservation_ids waits for Maya's
    write lock and then hands him R102. His INSERT is refused by the no-overlap trigger, not by the
    primary key: 409 Unavailable, the answer a guest should get.
    """
    database = tmp_path / "hotel.sqlite3"
    app, _ = main.build_api(main.sqlite_connector(database), sender=SlowSender())
    answers = race(TestClient(app, raise_server_exceptions=False), omar_after=0.1)
    assert answers == {"Maya": (201, "R101"), "Omar": (409, "Unavailable")}
    assert confirmed_r7(database) == 1


def test_two_rooms_booked_at_the_same_moment_get_different_ids(tmp_path: Path) -> None:
    """No overlap, so both are accepted - and the id counter gives them R101 and R102, never R101 twice."""
    database = tmp_path / "hotel.sqlite3"
    client = client_over(database, slow_step_seconds=0.2)
    answers: dict[str, tuple[int, str]] = {}

    def book(name: str, guest_body: dict[str, str]) -> None:
        response = client.post("/reservations", json=guest_body)
        answers[name] = (response.status_code, response.json()["id"])

    r8 = {**body("omar-r7.json"), "room": "R8", "checkIn": "2026-11-12", "checkOut": "2026-11-14"}
    threads = [threading.Thread(target=book, args=("Maya", body("maya-r7.json"))),
               threading.Thread(target=book, args=("Omar", r8))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(answers.values()) == [(201, "R101"), (201, "R102")]


def test_the_database_refuses_a_double_booking_typed_straight_in(tmp_path: Path) -> None:
    """Step 7's "no code path can get round it", on SQLite: an INSERT that never touched the app."""
    database = tmp_path / "hotel.sqlite3"
    client_over(database).post("/reservations", json=body("maya-r7.json"))
    with closing(sqlite3.connect(database)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="^reservations_no_overlap: "):
            connection.execute("INSERT INTO reservations VALUES "
                               "('R999','Direct Insert','direct@example.com','R7','2026-11-13','2026-11-15','Confirmed')")
        connection.execute("INSERT INTO reservations VALUES "  # a Cancelled row blocks nothing
                           "('R998','Direct Insert','direct@example.com','R7','2026-11-13','2026-11-15','Cancelled')")
        with pytest.raises(sqlite3.IntegrityError, match="^reservations_no_overlap: "):
            connection.execute("UPDATE reservations SET status = 'Confirmed' WHERE id = 'R998'")


V5_SCHEMA = """
CREATE TABLE rooms (number text PRIMARY KEY, type text NOT NULL);
CREATE TABLE reservations (
    id text PRIMARY KEY, guest_name text NOT NULL, guest_email text NOT NULL, room text NOT NULL,
    check_in date NOT NULL, check_out date NOT NULL,
    status text NOT NULL CHECK (status IN ('Confirmed', 'Cancelled')), CHECK (check_out > check_in));
INSERT INTO rooms VALUES ('R7', 'Standard'), ('R8', 'Deluxe');
INSERT INTO reservations VALUES ('R101','Maya','maya@example.com','R7','2026-11-12','2026-11-14','Confirmed');
INSERT INTO reservations VALUES ('R102','Omar','omar@example.com','R7','2026-11-12','2026-11-14','Confirmed');
"""


def test_a_version_5_file_with_a_double_booking_is_not_upgraded_until_it_is_cleaned(tmp_path: Path) -> None:
    """Step 7.1 on SQLite: the rule cannot be switched on over data that already breaks it."""
    database = tmp_path / "hotel.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(V5_SCHEMA)  # what the race left behind in version 5
    with pytest.raises(main.UpgradeRefused, match="R101 and R102 both have R7"):
        main.sqlite_connector(database)
    with closing(sqlite3.connect(database)) as connection:  # nothing was changed by the refusal
        names = {name for (name,) in connection.execute("SELECT name FROM sqlite_master")}
        assert "reservation_ids" not in names and "reservations_no_overlap_insert" not in names
        connection.execute("UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102'")  # Step 7.2
        connection.commit()
    client = client_over(database)  # now it upgrades
    assert answer(client.post("/reservations", json=body("omar-r7.json"))) == (
        409, '{"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}')
    created = client.post("/reservations", json={**body("omar-r7.json"), "room": "R8"})
    assert (created.status_code, created.json()["id"]) == (201, "R103")  # the counter starts above R102


def test_slow_step_and_port_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 1.3: HOTEL_SLOW_STEP and HOTEL_PORT reach the server (the flags win over them)."""
    monkeypatch.setenv("HOTEL_SLOW_STEP", "1")
    monkeypatch.setenv("HOTEL_PORT", "5081")
    started: list[main.ServerOptions] = []
    main.main([], serve=started.append)
    main.main(["--port", "5082", "--slow-step", "0.5"], serve=started.append)
    assert started == [main.ServerOptions("sqlite", 5081, "redis", True, 1.0),
                       main.ServerOptions("sqlite", 5082, "redis", True, 0.5)]


def test_main_without_a_flag_starts_the_web_app(capsys: pytest.CaptureFixture[str]) -> None:
    started: list[main.ServerOptions] = []
    main.main([], serve=started.append)
    assert started == [main.ServerOptions("sqlite", 5080, "redis", True)]
    assert capsys.readouterr().out == ""


def test_main_db_and_port_options_reach_the_server() -> None:
    started: list[main.ServerOptions] = []
    main.main(["--db", "postgres", "--port", "5081"], serve=started.append)
    assert started == [main.ServerOptions("postgres", 5081, "redis", True)]
