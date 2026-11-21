"""P09 - protect the last seat: the store keeps R3 when two requests check at the same moment.

The race of P03-P08 had one cause: ``BookingService.reserve`` checks (``has_overlap``) and then
saves, and another request fits in between (write skew, docs/interleaving.md). P09 makes the
store's ``save`` refuse a reservation that would double-book its room. These tests check that
promise where it is kept and how it is kept:

1. The promise itself, on both stores (list and SQL): ``save`` refuses an overlap even when nothing
   asked ``has_overlap`` first; a refusal keeps nothing; a Cancelled reservation blocks nothing; a
   duplicate id is a *different* error. ``next_reservation_id`` never hands out a number twice.
2. Under real concurrency: many threads (list store) and many SQLite connections (SQL store) all
   pass the pre-check before anyone saves - exactly one reservation is kept. Each test also runs
   the version-5 behaviour (no check in ``save``, or the triggers dropped) and sees the double
   booking, so it is known that the test *can* fail.
3. The PostgreSQL path of the SQL store, with a scripted DB-API connection (psycopg is not
   installable here): ``nextval``, the savepoint around the INSERT, that only SQLSTATE 23P01 on
   ``reservations_no_overlap`` becomes ``OverlapRejected``, and the bounded retry after a deadlock
   (40P01) between two conflicting INSERTs - found in the P09 burst runs on PostgreSQL 16. The same statements were run on a real
   PostgreSQL 16 server (practices/P09-protect-the-last-seat/evidence).
4. ``BookingService`` turns the refusal into Unavailable and sends no confirmation.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from hotel_booking.demo import HOTEL_ROOMS, MAYA, NORA, OMAR, R7, R8, nov
from hotel_booking.notifications import Confirmation
from hotel_booking.reservations import (
    BookingOutcome,
    BookingService,
    DateRange,
    Guest,
    OverlapRejected,
    Reservation,
    ReservationStore,
)
from hotel_booking.reservations.internal import (
    NO_OVERLAP_CONSTRAINT,
    InMemoryReservationStore,
    SqlReservationStore,
    is_overlap_refusal,
)
from main import sqlite_connector

StoreFactory = Callable[[], ReservationStore]


@pytest.fixture
def connect(tmp_path: Path) -> Callable[[], sqlite3.Connection]:
    return sqlite_connector(tmp_path / "hotel.sqlite3")


@pytest.fixture(params=["list", "sql"])
def new_store(request: pytest.FixtureRequest, connect: Callable[[], sqlite3.Connection]) -> Iterator[StoreFactory]:
    if request.param == "list":
        yield InMemoryReservationStore
        return
    with closing(connect()) as connection:
        yield lambda: SqlReservationStore(connection, HOTEL_ROOMS)


def r7(reservation_id: str, guest: Guest, stay: DateRange) -> Reservation:
    return Reservation(reservation_id, guest, R7, stay)


def duplicate_id_error(store: ReservationStore) -> type[Exception]:
    return sqlite3.IntegrityError if isinstance(store, SqlReservationStore) else ValueError


# --------------------------------------------------------------------------- 1. the promise


@pytest.mark.parametrize("stay", [nov(12, 14), nov(13, 15), nov(11, 13), nov(10, 16)])
def test_save_refuses_an_overlap_even_without_the_pre_check(new_store: StoreFactory, stay: DateRange) -> None:
    """The course's second P09 test, on both stores and four kinds of overlap. Nothing calls has_overlap."""
    store = new_store()
    store.save(r7("R101", MAYA, nov(12, 14)))
    with pytest.raises(OverlapRejected, match="R7"):
        store.save(r7("R102", OMAR, stay))
    assert store.count() == 1 and store.find("R102") is None
    assert store.count_confirmed(R7, nov(10, 16)) == 1


@pytest.mark.parametrize("stay", [nov(14, 16), nov(10, 12)])
def test_an_adjacent_stay_is_not_an_overlap(new_store: StoreFactory, stay: DateRange) -> None:
    """Half-open, like DateRange and the constraint's '[)': check-out day = next check-in day is fine."""
    store = new_store()
    store.save(r7("R101", MAYA, nov(12, 14)))
    store.save(r7("R102", NORA, stay))
    assert store.count() == 2


def test_another_room_is_never_an_overlap(new_store: StoreFactory) -> None:
    store = new_store()
    store.save(r7("R101", MAYA, nov(12, 14)))
    store.save(Reservation("R102", OMAR, R8, nov(12, 14)))
    assert store.count() == 2


def test_a_cancelled_reservation_blocks_nothing(new_store: StoreFactory) -> None:
    store = new_store()
    store.save(r7("R101", MAYA, nov(12, 14)))
    found = store.find("R101")
    assert found is not None and found.cancel()
    if isinstance(store, SqlReservationStore):
        store.save_changes()
    store.save(r7("R102", OMAR, nov(12, 14)))  # the guest can rebook a stay that was cancelled
    assert store.count_confirmed(R7, nov(12, 14)) == 1


def test_a_duplicate_id_is_a_fault_not_a_full_room(new_store: StoreFactory) -> None:
    """The primary key's job (or the list's), and never reported as OverlapRejected."""
    store = new_store()
    store.save(r7("R101", MAYA, nov(12, 14)))
    with pytest.raises(duplicate_id_error(store)) as raised:
        store.save(Reservation("R101", OMAR, R8, nov(20, 22)))
    assert not isinstance(raised.value, OverlapRejected)


def test_ids_come_from_the_store_and_are_never_handed_out_twice(new_store: StoreFactory) -> None:
    store = new_store()
    first, second = store.next_reservation_id(), store.next_reservation_id()
    assert (first, second) == ("R101", "R102")
    store.save(r7(second, MAYA, nov(12, 14)))
    assert store.next_reservation_id() == "R103"  # R101 was handed out and not used: it stays used


def test_a_refused_booking_uses_up_its_number_like_a_sequence(new_store: StoreFactory) -> None:
    store = new_store()
    store.save(r7(store.next_reservation_id(), MAYA, nov(12, 14)))
    refused = store.next_reservation_id()
    with pytest.raises(OverlapRejected):
        store.save(r7(refused, OMAR, nov(12, 14)))
    assert (refused, store.next_reservation_id()) == ("R102", "R103")


def test_the_list_store_never_hands_out_a_number_it_has_seen_saved() -> None:
    store = InMemoryReservationStore()
    store.save(r7("R105", MAYA, nov(12, 14)))  # saved with an id from elsewhere (a test, an import)
    assert store.next_reservation_id() == "R106"


# --------------------------------------------------------------------------- 2. under real concurrency


class UncheckedListStore(InMemoryReservationStore):
    """Version 5's save: append, no check, no lock. Shows the threaded test can see a double booking."""

    def save(self, reservation: Reservation) -> None:
        self._rows.append(reservation)


def everyone_checks_then_everyone_saves(make_store: Callable[[], ReservationStore], requests: int,
                                        finish: Callable[[ReservationStore], None] = lambda store: None) -> list[str]:
    """``requests`` threads each check R7 for 12-14 Nov, wait until *all* have checked, then save.

    That is the worst interleaving there is: every pre-check says "free". ``finish`` ends one
    request in its own thread (the SQL store: commit and close). Returns each thread's outcome:
    "saved", "refused" (OverlapRejected) or the name of any other error.
    """
    everyone_checked = threading.Barrier(requests)
    outcomes: list[str] = []
    lock = threading.Lock()

    def request(number: int) -> None:
        store = make_store()
        assert not store.has_overlap(R7, nov(12, 14))
        everyone_checked.wait(timeout=10)
        try:
            store.save(r7(store.next_reservation_id(), Guest(f"Guest {number}", "g@example.com"), nov(12, 14)))
            outcome = "saved"
        except OverlapRejected:
            outcome = "refused"
        except Exception as error:  # noqa: BLE001 - reported, not hidden
            outcome = type(error).__name__
        finish(store)
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=request, args=(number,)) for number in range(requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


def test_fifty_threads_on_the_list_store_one_reservation() -> None:
    shared = InMemoryReservationStore()
    outcomes = everyone_checks_then_everyone_saves(lambda: shared, 50)
    assert outcomes == ["refused"] * 49 + ["saved"]
    assert shared.count_confirmed(R7, nov(12, 14)) == 1


def test_fifty_threads_on_a_list_store_without_the_lock_double_book() -> None:
    """The control: without the check in save the same test sees 50 Confirmed reservations."""
    shared = UncheckedListStore()
    assert everyone_checks_then_everyone_saves(lambda: shared, 50) == ["saved"] * 50
    assert shared.count_confirmed(R7, nov(12, 14)) == 50


def test_fifty_threads_get_fifty_different_ids() -> None:
    store = InMemoryReservationStore()
    ids: list[str] = []
    start = threading.Barrier(50)

    def take() -> None:
        start.wait(timeout=10)
        ids.append(store.next_reservation_id())

    threads = [threading.Thread(target=take) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(ids, key=lambda text: int(text[1:])) == [f"R{number}" for number in range(101, 151)]


def commit_and_close(store: ReservationStore) -> None:
    """The end of a request in the wiring's unit of work: COMMIT (also after a refusal), then close."""
    assert isinstance(store, SqlReservationStore)
    store.save_changes()
    store._connection.close()  # tests may look inside: there is no public close on the store


def sql_store(connect: Callable[[], sqlite3.Connection]) -> Callable[[], ReservationStore]:
    """Like the wiring: every request gets its own connection (= its own transaction) and store."""
    return lambda: SqlReservationStore(connect(), HOTEL_ROOMS)


def confirmed_rows(connect: Callable[[], sqlite3.Connection]) -> list[tuple[str, str]]:
    with closing(connect()) as connection:
        return connection.execute("SELECT id, status FROM reservations WHERE status = 'Confirmed' ORDER BY id").fetchall()


def test_eight_connections_on_sqlite_one_reservation_and_eight_different_ids(
    connect: Callable[[], sqlite3.Connection],
) -> None:
    """Eight requests, eight connections, all pre-checks before any save: the trigger keeps one."""
    outcomes = everyone_checks_then_everyone_saves(sql_store(connect), 8, commit_and_close)
    assert outcomes == ["refused"] * 7 + ["saved"]
    assert len(confirmed_rows(connect)) == 1
    with closing(connect()) as connection:  # every request drew its own number; none was given twice
        assert connection.execute("SELECT last_value FROM reservation_ids").fetchone() == (108,)


def test_eight_connections_on_sqlite_without_the_triggers_double_book(connect: Callable[[], sqlite3.Connection]) -> None:
    """The control: the same test with the version-5 schema rule (no triggers) keeps all eight."""
    with closing(connect()) as connection:
        connection.executescript("DROP TRIGGER reservations_no_overlap_insert; DROP TRIGGER reservations_no_overlap_update;")
    outcomes = everyone_checks_then_everyone_saves(sql_store(connect), 8, commit_and_close)
    assert outcomes == ["saved"] * 8
    assert len(confirmed_rows(connect)) == 8


# --------------------------------------------------------------------------- 3. the PostgreSQL path


@dataclass
class Diagnostics:
    constraint_name: str | None


class FakePsycopgError(Exception):
    """The two attributes psycopg 3 errors carry that the store reads: sqlstate and diag.constraint_name."""

    def __init__(self, sqlstate: str, constraint_name: str | None, message: str) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.diag = Diagnostics(constraint_name)


@dataclass
class ScriptedConnection:
    """A DB-API connection that records every statement and answers or fails as scripted."""

    fail_insert_with: Exception | None = None
    statements: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    next_value: int = 101

    def cursor(self) -> ScriptedCursor:
        return ScriptedCursor(self)


class ScriptedCursor:
    def __init__(self, connection: ScriptedConnection) -> None:
        self._connection = connection
        self.description: tuple[str, ...] | None = None
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        self._connection.statements.append((sql, params))
        self.description, self._rows = None, []
        if sql.startswith("INSERT") and self._connection.fail_insert_with is not None:
            raise self._connection.fail_insert_with
        if sql.startswith("SELECT nextval"):
            self.description, self._rows = ("nextval",), [(self._connection.next_value,)]
            self._connection.next_value += 1

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    def close(self) -> None:
        pass


def postgres_store(connection: ScriptedConnection) -> SqlReservationStore:
    return SqlReservationStore(connection, HOTEL_ROOMS)  # not sqlite3.Connection -> the PostgreSQL dialect


def test_postgres_ids_come_from_the_sequence() -> None:
    connection = ScriptedConnection()
    store = postgres_store(connection)
    assert [store.next_reservation_id(), store.next_reservation_id()] == ["R101", "R102"]
    assert [sql for sql, _ in connection.statements] == ["SELECT nextval('reservation_ids')"] * 2


def test_postgres_insert_runs_inside_a_savepoint() -> None:
    connection = ScriptedConnection()
    postgres_store(connection).save(r7("R101", MAYA, nov(12, 14)))
    sqls = [sql for sql, _ in connection.statements]
    assert sqls[0] == "SAVEPOINT reservation_insert" and sqls[2] == "RELEASE SAVEPOINT reservation_insert"
    assert sqls[1].startswith("INSERT INTO reservations") and "%s" in sqls[1] and "?" not in sqls[1]
    assert connection.statements[1][1][4:6] == (nov(12, 14).check_in, nov(12, 14).check_out)  # real dates


def test_postgres_exclusion_violation_becomes_overlap_rejected_and_the_transaction_survives() -> None:
    refusal = FakePsycopgError("23P01", NO_OVERLAP_CONSTRAINT,
                               'conflicting key value violates exclusion constraint "reservations_no_overlap"')
    connection = ScriptedConnection(fail_insert_with=refusal)
    with pytest.raises(OverlapRejected) as raised:
        postgres_store(connection).save(r7("R102", OMAR, nov(12, 14)))
    assert raised.value.__cause__ is refusal
    assert [sql.split(" (")[0] for sql, _ in connection.statements] == [
        "SAVEPOINT reservation_insert", "INSERT INTO reservations", "ROLLBACK TO SAVEPOINT reservation_insert"]


@pytest.mark.parametrize("error", [
    FakePsycopgError("23505", "reservations_pkey", "duplicate key value violates unique constraint"),
    FakePsycopgError("23P01", "some_other_exclusion", "another exclusion constraint"),
    FakePsycopgError("08006", None, "server closed the connection unexpectedly"),
], ids=["duplicate id", "other constraint", "lost connection"])
def test_postgres_any_other_error_is_re_raised_untouched(error: FakePsycopgError) -> None:
    connection = ScriptedConnection(fail_insert_with=error)
    with pytest.raises(FakePsycopgError) as raised:
        postgres_store(connection).save(r7("R101", MAYA, nov(12, 14)))
    assert raised.value is error and not isinstance(raised.value, OverlapRejected)
    assert connection.statements[-1][0] == "ROLLBACK TO SAVEPOINT reservation_insert"


def deadlock() -> FakePsycopgError:
    return FakePsycopgError("40P01", None, "deadlock detected")


def scripted_inserts(*outcomes: Exception | None) -> ScriptedConnection:
    """A connection whose successive INSERTs raise the given errors (None = the INSERT succeeds)."""
    connection = ScriptedConnection()
    remaining = list(outcomes)
    original_execute = ScriptedCursor.execute

    class Cursor(ScriptedCursor):
        def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
            if sql.startswith("INSERT"):
                connection.statements.append((sql, params))
                outcome = remaining.pop(0)
                if outcome is not None:
                    raise outcome
                return
            original_execute(self, sql, params)

    connection.cursor = lambda: Cursor(connection)  # type: ignore[method-assign]
    return connection


def test_postgres_deadlock_between_two_inserts_is_retried_and_ends_as_a_409() -> None:
    """Seen in the P09 burst runs: 40P01 instead of 23P01. Retried, the INSERT gets the real answer."""
    refusal = FakePsycopgError("23P01", NO_OVERLAP_CONSTRAINT, "conflicting key value")
    connection = scripted_inserts(deadlock(), refusal)
    with pytest.raises(OverlapRejected):
        postgres_store(connection).save(r7("R102", OMAR, nov(12, 14)))
    assert [sql.split(" (")[0] for sql, _ in connection.statements] == [
        "SAVEPOINT reservation_insert", "INSERT INTO reservations", "ROLLBACK TO SAVEPOINT reservation_insert",
        "SAVEPOINT reservation_insert", "INSERT INTO reservations", "ROLLBACK TO SAVEPOINT reservation_insert"]


def test_postgres_deadlock_whose_other_booking_rolled_back_ends_saved() -> None:
    connection = scripted_inserts(deadlock(), None)
    postgres_store(connection).save(r7("R101", MAYA, nov(12, 14)))
    assert connection.statements[-1][0] == "RELEASE SAVEPOINT reservation_insert"


def test_postgres_deadlock_retries_are_limited() -> None:
    connection = scripted_inserts(deadlock(), deadlock(), deadlock())
    with pytest.raises(FakePsycopgError) as raised:
        postgres_store(connection).save(r7("R101", MAYA, nov(12, 14)))
    assert raised.value.sqlstate == "40P01"
    assert sum(sql.startswith("INSERT") for sql, _ in connection.statements) == 3


def test_only_the_named_refusal_is_recognised(connect: Callable[[], sqlite3.Connection]) -> None:
    with closing(connect()) as connection:
        connection.execute("INSERT INTO reservations VALUES ('R101','Maya','m@x','R7','2026-11-12','2026-11-14','Confirmed')")
        errors: list[sqlite3.IntegrityError] = []
        for row in ("('R102','Omar','o@x','R7','2026-11-13','2026-11-15','Confirmed')",   # the trigger
                    "('R101','Omar','o@x','R8','2026-11-13','2026-11-15','Confirmed')",   # primary key
                    "('R103','Omar','o@x','R8','2026-11-15','2026-11-15','Confirmed')"):  # CHECK
            with pytest.raises(sqlite3.IntegrityError) as raised:
                connection.execute(f"INSERT INTO reservations VALUES {row}")
            errors.append(raised.value)
    assert [is_overlap_refusal(error) for error in errors] == [True, False, False]
    assert [error.sqlite_errorname for error in errors] == [
        "SQLITE_CONSTRAINT_TRIGGER", "SQLITE_CONSTRAINT_PRIMARYKEY", "SQLITE_CONSTRAINT_CHECK"]
    assert not is_overlap_refusal(RuntimeError(NO_OVERLAP_CONSTRAINT))


# --------------------------------------------------------------------------- 4. BookingService


class LosingStore(InMemoryReservationStore):
    """The moment of the race, frozen: the pre-check says free, then someone else saves first."""

    def has_overlap(self, room: Any, stay: DateRange) -> bool:
        return False

    def save(self, reservation: Reservation) -> None:
        raise OverlapRejected("R7 already has a Confirmed reservation for at least one of these nights.")


class CountingSender:
    def __init__(self) -> None:
        self.sent: list[Confirmation] = []

    def send_confirmation(self, confirmation: Confirmation) -> None:
        self.sent.append(confirmation)


def test_a_refused_save_is_answered_unavailable_and_nobody_is_told_confirmed(caplog: pytest.LogCaptureFixture) -> None:
    sender = CountingSender()
    service = BookingService(HOTEL_ROOMS, LosingStore(), sender)
    with caplog.at_level(logging.INFO, logger="hotel_booking.reservations.booking"):
        result = service.reserve(OMAR, R7, nov(12, 14))
    assert (result.outcome, result.reservation_id, result.notification_failed) == (BookingOutcome.UNAVAILABLE, None, False)
    assert str(result) == "Unavailable" and sender.sent == []
    assert "lost the race" in caplog.text


def test_other_store_errors_are_not_turned_into_unavailable() -> None:
    """A fault must stay a fault (500 at the edge), not become "the room is taken"."""

    class BrokenStore(InMemoryReservationStore):
        def save(self, reservation: Reservation) -> None:
            raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(sqlite3.OperationalError):
        BookingService(HOTEL_ROOMS, BrokenStore(), CountingSender()).reserve(MAYA, R7, nov(12, 14))
