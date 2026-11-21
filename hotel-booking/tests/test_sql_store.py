"""The SQL store and catalog keep the same promises as the lists (P07 Step 7), on SQLite.

1. One contract suite, run against *both* ``ReservationStore`` implementations (the list and the
   SQL store): a substitute must give the same answers (Liskov; P04's substitution rule).
2. What only a database store has: data that outlives the connection (the restart), the unit of
   work (``save_changes`` writes only what changed; a rollback leaves nothing), the identity map,
   the rules the database keeps by itself (primary key, CHECK), bound parameters.
3. One schema for both databases: until P08 SQLite ran the very file docker-compose mounts into
   PostgreSQL; since P09 it runs its translation (db/sqlite/init.sql), and the checks here keep
   the two files declaring the same tables, columns, CHECKs, index and rooms.
4. The capacity model's assumption "a search asks the database once per room" (docs/capacity.md),
   counted on the real SQL with SQLite's trace hook.

PostgreSQL itself is not reachable from these tests (no driver in the build container); the same
SQL statements were run on a real PostgreSQL 16 server with psql - see the P07 evidence (E9).

P09 changes (deliberate): (a) ``test_save_changes_writes_only_the_statuses_that_changed`` counts
the rows the UPDATE changed instead of the traced UPDATE lines - SQLite's trace hook reports the
statement a second time when the no-overlap UPDATE trigger starts, although one row is written
once. (b) ``test_sqlite_runs_the_file_docker_compose_mounts_into_postgresql`` became
``test_sqlite_and_postgresql_schemas_declare_the_same_tables`` plus two checks of the
PostgreSQL-only statements and their SQLite counterparts. (c) The SQLite schema now has a third
table, ``reservation_ids`` (SQLite's stand-in for the sequence), owned by Reservations. The new
promises (``save`` refuses an overlap, ``next_reservation_id``) are tested in tests/test_concurrency.py.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from hotel_booking.demo import HOTEL_ROOMS, MAYA, NORA, OMAR, R7, R8, nov
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, DateRange, Reservation, ReservationStatus, ReservationStore
from hotel_booking.reservations.internal import InMemoryReservationStore, SqlReservationStore, as_date
from hotel_booking.rooms import Room
from hotel_booking.rooms.internal import SqlRoomCatalog
from main import POSTGRES_SCHEMA, SCHEMA, SQLITE_UPGRADE, sqlite_connector

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def connect(tmp_path: Path) -> Callable[[], sqlite3.Connection]:
    """A fresh database file with the init.sql tables, R7 and R8 (the main.py SQLite wiring)."""
    return sqlite_connector(tmp_path / "hotel.sqlite3")  # type: ignore[no-any-return]


@pytest.fixture
def connection(connect: Callable[[], sqlite3.Connection]) -> Iterator[sqlite3.Connection]:
    with closing(connect()) as opened:
        yield opened


StoreFactory = Callable[[], ReservationStore]


@pytest.fixture(params=["list", "sql"])
def new_store(request: pytest.FixtureRequest, connection: sqlite3.Connection) -> StoreFactory:
    if request.param == "list":
        return InMemoryReservationStore
    return lambda: SqlReservationStore(connection, HOTEL_ROOMS)


def maya_r7(reservation_id: str = "R101", stay: DateRange | None = None) -> Reservation:
    return Reservation(reservation_id, MAYA, R7, stay or nov(12, 14))


# --------------------------------------------------------------------------- 1. the same promise


def test_an_empty_store_has_nothing(new_store: StoreFactory) -> None:
    store = new_store()
    assert store.count() == 0
    assert store.find("R101") is None
    assert not store.has_overlap(R7, nov(12, 14))


def test_saved_reservation_is_found_with_all_its_facts(new_store: StoreFactory) -> None:
    store = new_store()
    store.save(maya_r7())
    found = store.find("R101")
    assert found is not None
    assert (found.id, found.guest, found.room, found.stay, found.status) == (
        "R101", MAYA, R7, nov(12, 14), ReservationStatus.CONFIRMED)
    assert store.count() == 1


@pytest.mark.parametrize(("stay", "overlaps"), [
    (nov(12, 14), True), (nov(13, 15), True), (nov(10, 13), True), (nov(11, 16), True),
    (nov(14, 16), False), (nov(10, 12), False), (nov(20, 22), False),
])
def test_overlap_is_the_half_open_rule(new_store: StoreFactory, stay: DateRange, overlaps: bool) -> None:
    store = new_store()
    store.save(maya_r7())
    assert store.has_overlap(R7, stay) is overlaps
    assert store.count_confirmed(R7, stay) == int(overlaps)
    assert not store.has_overlap(R8, stay)


def test_a_cancelled_reservation_no_longer_blocks(new_store: StoreFactory) -> None:
    store = new_store()
    store.save(maya_r7())
    found = store.find("R101")
    assert found is not None and found.cancel()
    if isinstance(store, SqlReservationStore):
        store.save_changes()
    assert not store.has_overlap(R7, nov(12, 14))
    assert store.count() == 1  # history is kept


def test_booking_service_gives_the_same_records_on_both_stores(new_store: StoreFactory) -> None:
    """The demo scenario through BookingService: the answers do not depend on the store."""
    store = new_store()
    service = BookingService(HOTEL_ROOMS, store, EmailNotificationSender())
    answers = [
        str(service.reserve(MAYA, R7, nov(12, 14))), str(service.reserve(OMAR, R7, nov(13, 15))),
        str(service.reserve(NORA, R7, nov(14, 16))), str(service.reserve(OMAR, R8, nov(15, 15))),
        [room.number for room in service.find_free_rooms(nov(12, 14))], service.cancel("R101"),
        service.cancel("R101"), service.cancel("R999"),
        [room.number for room in service.find_free_rooms(nov(12, 14))],
    ]
    assert answers == ["Accepted R101", "Unavailable", "Accepted R102", "InvalidDates", ["R8"],
                       True, False, False, ["R7", "R8"]]


# --------------------------------------------------------------------------- 2. what a database adds


def test_bookings_survive_a_new_connection_the_restart(connect: Callable[[], sqlite3.Connection]) -> None:
    with closing(connect()) as first:
        store = SqlReservationStore(first, HOTEL_ROOMS)
        store.save(maya_r7())
        store.save_changes()
    with closing(connect()) as after_restart:
        again = SqlReservationStore(after_restart, HOTEL_ROOMS)
        assert again.count() == 1 and again.has_overlap(R7, nov(12, 14))


def test_without_save_changes_nothing_is_kept(connect: Callable[[], sqlite3.Connection]) -> None:
    with closing(connect()) as first:
        SqlReservationStore(first, HOTEL_ROOMS).save(maya_r7())
        first.rollback()  # what the unit of work does when the request failed
    with closing(connect()) as second:
        assert SqlReservationStore(second, HOTEL_ROOMS).count() == 0


def test_save_changes_writes_only_the_statuses_that_changed(connection: sqlite3.Connection) -> None:
    store = SqlReservationStore(connection, HOTEL_ROOMS)
    store.save(maya_r7())
    store.save(Reservation("R102", NORA, R8, nov(12, 14)))
    assert store.save_changes() == 0  # inserts are already written; no status changed
    reader = SqlReservationStore(connection, HOTEL_ROOMS)
    found = reader.find("R101")
    assert found is not None and found.cancel()
    reader.find("R102")  # looked at, not changed
    statements: list[str] = []
    changes_before = connection.total_changes
    connection.set_trace_callback(statements.append)
    assert reader.save_changes() == 1
    connection.set_trace_callback(None)
    assert connection.total_changes - changes_before == 1  # one row written
    assert {s for s in statements if s.startswith("UPDATE")} == {
        "UPDATE reservations SET status = 'Cancelled' WHERE id = 'R101'"}  # (traced twice: the trigger)
    assert reader.save_changes() == 0  # in sync now: saving twice writes nothing twice


def test_find_twice_gives_the_same_object_in_one_unit_of_work(connection: sqlite3.Connection) -> None:
    store = SqlReservationStore(connection, HOTEL_ROOMS)
    store.save(maya_r7())
    store.save_changes()
    fresh = SqlReservationStore(connection, HOTEL_ROOMS)
    first, second = fresh.find("R101"), fresh.find("R101")
    assert first is second and first is not None
    assert first.cancel() and not second.cancel()  # so a double cancel in one request is still refused


def test_a_cancelled_row_comes_back_cancelled(connection: sqlite3.Connection) -> None:
    connection.execute("INSERT INTO reservations VALUES ('R101','Maya','maya@example.com','R7','2026-11-12','2026-11-14','Cancelled')")
    found = SqlReservationStore(connection, HOTEL_ROOMS).find("R101")
    assert found is not None and found.status is ReservationStatus.CANCELLED
    assert not found.cancel()


def test_the_primary_key_refuses_a_second_r101(connection: sqlite3.Connection) -> None:
    """Two app instances that both counted 0 reservations both try R101: the database says no."""
    SqlReservationStore(connection, HOTEL_ROOMS).save(maya_r7())
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: reservations.id"):
        SqlReservationStore(connection, HOTEL_ROOMS).save(Reservation("R101", OMAR, R8, nov(20, 22)))


@pytest.mark.parametrize(("row", "message"), [
    ("('R102','Omar','omar@example.com','R8','2026-11-15','2026-11-15','Confirmed')", "CHECK constraint failed"),
    ("('R103','Omar','omar@example.com','R8','2026-11-15','2026-11-17','Pending')", "CHECK constraint failed"),
    ("('R104',NULL,'omar@example.com','R8','2026-11-15','2026-11-17','Confirmed')", "NOT NULL constraint failed"),
])
def test_the_database_refuses_a_wrong_row_by_itself(connection: sqlite3.Connection, row: str, message: str) -> None:
    with pytest.raises(sqlite3.IntegrityError, match=message):
        connection.execute(f"INSERT INTO reservations VALUES {row}")


def test_values_are_bound_parameters_not_sql(connection: sqlite3.Connection) -> None:
    store = SqlReservationStore(connection, HOTEL_ROOMS)
    store.save(Reservation("R101", MAYA, R7, nov(12, 14)))
    assert store.find("R101' OR '1'='1") is None
    assert not store.has_overlap(Room("R7' OR '1'='1", "Standard"), nov(12, 14))
    store.save(Reservation("R102", type(MAYA)("Robert'); DROP TABLE reservations;--", "x@example.com"), R8, nov(12, 14)))
    assert store.count() == 2


def test_a_row_for_a_room_the_catalog_does_not_sell_is_reported(connection: sqlite3.Connection) -> None:
    connection.execute("INSERT INTO reservations VALUES ('R101','Maya','maya@example.com','R99','2026-11-12','2026-11-14','Confirmed')")
    with pytest.raises(LookupError, match="R99"):
        SqlReservationStore(connection, HOTEL_ROOMS).find("R101")


def test_dates_come_back_as_dates() -> None:
    assert as_date("2026-11-12") == date(2026, 11, 12) == as_date(date(2026, 11, 12))
    with pytest.raises(TypeError):
        as_date(20261112)


def test_sql_room_catalog_reads_the_rooms_table_in_text_order(connection: sqlite3.Connection) -> None:
    assert SqlRoomCatalog(connection).all() == [R7, R8]
    connection.execute("INSERT INTO rooms VALUES ('R10', 'Suite')")
    assert [room.number for room in SqlRoomCatalog(connection).all()] == ["R10", "R7", "R8"]


# --------------------------------------------------------------------------- 3. one schema for both databases


def table_definitions(sql: str) -> dict[str, list[str]]:
    """CREATE TABLE name -> its column and CHECK lines (comments, constraint blocks and spacing removed)."""
    tables: dict[str, list[str]] = {}
    for name, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.DOTALL):
        lines = [re.sub(r"\s+", " ", line.split("--")[0]).strip().rstrip(",") for line in body.splitlines()]
        kept, in_constraint = [], False
        for line in lines:
            if line.startswith("CONSTRAINT"):
                in_constraint = True
            if line and not in_constraint:
                kept.append(line)
            if in_constraint and line.startswith(")"):
                in_constraint = False
        tables[name] = kept
    return tables


def test_sqlite_and_postgresql_schemas_declare_the_same_tables() -> None:
    compose = (PROJECT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "./db/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" in compose
    assert (SCHEMA, POSTGRES_SCHEMA) == (PROJECT / "db" / "sqlite" / "init.sql", PROJECT / "db" / "postgres" / "init.sql")
    sqlite_sql, postgres_sql = SCHEMA.read_text(encoding="utf-8"), POSTGRES_SCHEMA.read_text(encoding="utf-8")
    sqlite_tables, postgres_tables = table_definitions(sqlite_sql), table_definitions(postgres_sql)
    assert sqlite_tables["rooms"] == postgres_tables["rooms"]
    assert sqlite_tables["reservations"] == postgres_tables["reservations"]
    index = re.compile(r"CREATE INDEX reservations_confirmed_room_stay.*?;", re.DOTALL)
    assert index.findall(sqlite_sql) == index.findall(postgres_sql) != []
    rooms = "INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe');"
    assert rooms in sqlite_sql and rooms in postgres_sql


def test_each_postgresql_only_statement_has_its_sqlite_counterpart() -> None:
    postgres_sql, sqlite_sql = POSTGRES_SCHEMA.read_text(encoding="utf-8"), SCHEMA.read_text(encoding="utf-8")
    # The rule: an exclusion constraint there, two triggers of the same name here.
    assert "CONSTRAINT reservations_no_overlap EXCLUDE USING gist" in postgres_sql
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist;" in postgres_sql
    assert re.findall(r"CREATE TRIGGER (reservations_no_overlap_\w+)", sqlite_sql) == [
        "reservations_no_overlap_insert", "reservations_no_overlap_update"]
    assert "WHERE (status = 'Confirmed')" in postgres_sql and sqlite_sql.count("NEW.status = 'Confirmed'") == 2
    # The ids: a sequence there, a one-row table of the same name here, both starting at 101.
    assert "CREATE SEQUENCE reservation_ids START 101;" in postgres_sql
    assert "INSERT INTO reservation_ids (only_row, last_value) VALUES (1, 100);" in sqlite_sql
    statements = "\n".join(line.split("--")[0] for line in sqlite_sql.splitlines()).upper()
    assert "EXCLUDE" not in statements and "SEQUENCE" not in statements  # nothing SQLite cannot run


def test_the_upgrade_files_add_exactly_what_init_sql_has() -> None:
    """A version-5 database upgraded with p09-upgrade.sql must end up with the same rule as a new one."""
    sqlite_init, sqlite_upgrade = SCHEMA.read_text(encoding="utf-8"), SQLITE_UPGRADE.read_text(encoding="utf-8")
    trigger = re.compile(r"CREATE TRIGGER .*?END;", re.DOTALL)
    assert trigger.findall(sqlite_upgrade) == trigger.findall(sqlite_init) != []
    postgres_init = POSTGRES_SCHEMA.read_text(encoding="utf-8")
    postgres_upgrade = (PROJECT / "db" / "postgres" / "p09-upgrade.sql").read_text(encoding="utf-8")
    rule = re.search(r"EXCLUDE USING gist \((.*?)\) WHERE \(status = 'Confirmed'\)", postgres_init, re.DOTALL)
    again = re.search(r"EXCLUDE USING gist \((.*?)\) WHERE \(status = 'Confirmed'\)", postgres_upgrade, re.DOTALL)
    assert rule is not None and again is not None
    assert re.sub(r"\s+", " ", rule.group(1)) == re.sub(r"\s+", " ", again.group(1))
    assert "ADD CONSTRAINT reservations_no_overlap" in postgres_upgrade and "setval('reservation_ids'" in postgres_upgrade


def test_schema_has_one_table_per_module_the_id_counter_and_no_foreign_key(connection: sqlite3.Connection) -> None:
    tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"rooms", "reservations", "reservation_ids"}  # P09: + Reservations' id counter
    assert connection.execute("PRAGMA foreign_key_list(reservations)").fetchall() == []
    assert connection.execute("SELECT number, type FROM rooms ORDER BY number").fetchall() == [("R7", "Standard"), ("R8", "Deluxe")]


def test_the_overlap_question_uses_the_partial_index(connection: sqlite3.Connection) -> None:
    plan = " ".join(str(row) for row in connection.execute(
        "EXPLAIN QUERY PLAN SELECT 1 FROM reservations WHERE room = 'R7' AND status = 'Confirmed' "
        "AND check_in < '2026-11-14' AND '2026-11-12' < check_out"))
    assert "reservations_confirmed_room_stay" in plan


def test_opening_an_existing_file_does_not_run_the_schema_again(tmp_path: Path) -> None:
    path = tmp_path / "hotel.sqlite3"
    with closing(sqlite_connector(path)()) as first:
        SqlReservationStore(first, HOTEL_ROOMS).save(maya_r7())
        first.commit()
    with closing(sqlite_connector(path)()) as again:  # the app started a second time
        assert SqlReservationStore(again, HOTEL_ROOMS).count() == 1


# --------------------------------------------------------------------------- 4. queries per search


@pytest.mark.parametrize("rooms", [2, 40])
def test_a_search_asks_the_database_once_per_room(connection: sqlite3.Connection, rooms: int) -> None:
    """docs/capacity.md assumes 40 queries per search for 40 rooms; counted here on the real SQL."""
    catalog = [Room(f"R{number}", "Standard") for number in range(1, rooms + 1)]
    statements: list[str] = []
    service = BookingService(catalog, SqlReservationStore(connection, catalog), EmailNotificationSender())
    connection.set_trace_callback(statements.append)
    service.find_free_rooms(nov(12, 14))
    connection.set_trace_callback(None)
    assert len(statements) == rooms
    assert all(statement.startswith("SELECT EXISTS") for statement in statements)
