"""Entry point of the hotel booking app (version 4, P07: the P06 modules behind an HTTP API, with a database).

    python main.py                  -> the HTTP API on http://localhost:5080, reservations in SQLite
                                       (file hotel.sqlite3 next to this file; HOTEL_DB_PATH changes it)
    python main.py --db postgres    -> the same API on PostgreSQL from docker-compose.yml
                                       (needs psycopg; HOTEL_DB_PORT if 5432 is taken)
    python main.py --demo           -> the P03-P06 demo (nine lines), data in lists
    python main.py --race           -> two guests book the same room at the same moment (lists)

This file is the *wiring* (composition root): the only application file that names internal
classes of the modules. P07 adds the web app's wiring: it reads the rooms once from the rooms
table, and for every request opens a connection, builds a ``SqlReservationStore`` and a
``BookingService`` over it, and at the end saves what changed (``save_changes``) or rolls back.
That is the unit of work; ``BookingService`` and the booking rule did not change.

P07 change (deliberate, as the activity sheet says): without an argument the program now starts
the web app; the demo moved to ``--demo``. The demo and the race keep their lists and their output.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette

from hotel_booking.api import UnitOfWork, create_app
from hotel_booking.demo import HOTEL_ROOMS, run_demo, run_race
from hotel_booking.notifications import NotificationSender
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore, SqlReservationStore
from hotel_booking.rooms import Room
from hotel_booking.rooms.internal import InMemoryRoomCatalog, SqlRoomCatalog

PROJECT = Path(__file__).resolve().parent
SCHEMA = PROJECT / "db" / "postgres" / "init.sql"
DEFAULT_SQLITE_PATH = PROJECT / "hotel.sqlite3"
HOST, PORT = "localhost", 5080
RACE_SLOW_STEP_SECONDS = 0.5  # widens the check-then-save gap so the race shows (demo only)

Connect = Callable[[], Any]  # opens a new DB-API 2 connection (sqlite3 or psycopg)


# --------------------------------------------------------------------------- console demo and race (lists)


def build_app(
    slow_step_seconds: float = 0.0,
) -> tuple[BookingService, InMemoryReservationStore, EmailNotificationSender]:
    """Create the real objects of every module and wire them together, with the data in lists.

    Returns the store and the sender too, because the demo reports what they hold.
    """
    catalog = InMemoryRoomCatalog(HOTEL_ROOMS)  # Rooms: R7 Standard, R8 Deluxe
    store = InMemoryReservationStore()          # Reservations' private rows
    email = EmailNotificationSender()           # Notifications: how the guest is told
    service = BookingService(catalog.all(), store, email, slow_step_seconds=slow_step_seconds)
    return service, store, email


# --------------------------------------------------------------------------- the web app (a database)


def sqlite_connector(path: Path) -> Connect:
    """Connections to one SQLite file; the first one creates the tables from db/postgres/init.sql."""
    def connect() -> sqlite3.Connection:
        # timeout: a writer waits up to 5 s for another request's write lock instead of failing.
        return sqlite3.connect(path, timeout=5.0)

    with closing(connect()) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reservations'").fetchone()
        if exists is None:
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))  # the same file PostgreSQL runs
    return connect


def postgres_connector(port: int) -> Connect:  # pragma: no cover - needs psycopg and a running PostgreSQL
    """Connections to PostgreSQL from docker-compose.yml (user, password and database: hotel).

    Proposed path for the student's Mac: psycopg cannot be installed in the build container, so this
    function is not run there (see the P07 README). The schema comes from docker-compose (init.sql).
    """
    import psycopg  # type: ignore[import-not-found,unused-ignore]  # optional: pip install "psycopg[binary]"

    url = f"postgresql://hotel:hotel@localhost:{port}/hotel"

    def connect() -> Any:
        return psycopg.connect(url)

    return connect


def sql_unit_of_work(
    connect: Connect, rooms: list[Room], sender: NotificationSender, slow_step_seconds: float = 0.0
) -> UnitOfWork:
    """One request = one connection, one store, one BookingService; save at the end or roll back."""
    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        connection = connect()
        try:
            store = SqlReservationStore(connection, rooms)
            yield BookingService(rooms, store, sender, slow_step_seconds=slow_step_seconds)
            store.save_changes()  # UPDATE what changed, then COMMIT
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    return unit_of_work


def build_api(
    connect: Connect, slow_step_seconds: float = 0.0, sender: NotificationSender | None = None
) -> tuple[Starlette, NotificationSender]:
    """The web app over a database: the rooms are read once, the reservations once per request.

    The email sender is the default; tests may hand in another ``NotificationSender``.
    """
    with closing(connect()) as connection:
        rooms = SqlRoomCatalog(connection).all()
    sender = sender or EmailNotificationSender()
    app = create_app(rooms, sql_unit_of_work(connect, rooms, sender, slow_step_seconds))
    return app, sender


def run_api(database: str, port: int = PORT) -> None:  # pragma: no cover - starts a server
    import uvicorn

    if database == "postgres":
        connect = postgres_connector(int(os.getenv("HOTEL_DB_PORT", "5432")))
    else:
        connect = sqlite_connector(Path(os.getenv("HOTEL_DB_PATH", str(DEFAULT_SQLITE_PATH))))
    app, _ = build_api(connect)
    uvicorn.run(app, host=HOST, port=port)


# --------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None, serve: Callable[[str, int], None] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Hotel booking app, version 4 (P07: HTTP API + database).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="print the nine demo lines (data in lists)")
    mode.add_argument("--race", action="store_true",
                      help="run two simultaneous bookings of R7 and show the double booking (data in lists)")
    parser.add_argument("--db", choices=("sqlite", "postgres"), default="sqlite",
                        help="the web app's database (default: sqlite)")
    parser.add_argument("--port", type=int, default=PORT, help=f"the web app's port (default: {PORT})")
    args = parser.parse_args(argv)
    if args.race:
        service, store, _ = build_app(slow_step_seconds=RACE_SLOW_STEP_SECONDS)
        run_race(service, store)
    elif args.demo:
        service, _, email = build_app()
        run_demo(service, lambda: email.sent)
    else:
        (serve or run_api)(args.db, args.port)


if __name__ == "__main__":
    main()
