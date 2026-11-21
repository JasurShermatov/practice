"""Entry point of the hotel booking app (version 6, P09: the booking rule protected by the database).

    python main.py                  -> the HTTP API on http://localhost:5080, reservations in SQLite
                                       (file hotel.sqlite3 next to this file; HOTEL_DB_PATH changes it),
                                       search cache in Redis on localhost:6379 (docker compose up -d;
                                       HOTEL_REDIS_HOST / HOTEL_REDIS_PORT change it)
    python main.py --db postgres    -> the same API on PostgreSQL from docker-compose.yml
                                       (needs psycopg; HOTEL_DB_PORT if 5432 is taken)
    python main.py --cache memory   -> the cache in this process instead of Redis (one instance only)
    python main.py --cache off      -> no cache: every search asks the database (the "No cache" run)
    python main.py --no-invalidation   P08 Step 5 experiment only: bookings do not invalidate the cache
    python main.py --demo           -> the P03-P06 demo (nine lines), data in lists
    python main.py --race           -> two guests book the same room at the same moment (lists):
                                       since P09 one gets it, the other is refused
    HOTEL_PORT=5081 python main.py  -> P09: a second instance on another port (or --port 5081)
    HOTEL_SLOW_STEP=1 python main.py   P09: every booking waits 1 s between its check and its save,
                                       so tools/race_http.py lands in the gap on every run

This file is the *wiring* (composition root): the only application file that names internal
classes of the modules. P07 adds the web app's wiring: it reads the rooms once from the rooms
table, and for every request opens a connection, builds a ``SqlReservationStore`` and a
``BookingService`` over it, and at the end saves what changed (``save_changes``) or rolls back.
That is the unit of work; ``BookingService`` and the booking rule did not change.

P07 change (deliberate, as the activity sheet says): without an argument the program now starts
the web app; the demo moved to ``--demo``. The demo and the race keep their lists and their output.

P08 change: the wiring counts the database questions (a ``CountingReservationStore`` around the
SQL store, sharing one ``Stats`` with GET /stats) and connects the search cache - Redis by
default, as the course does; the app stops at start-up if Redis does not answer PING. The server
options travel in one ``ServerOptions`` value (``main(serve=...)`` receives it).

P09 change: SQLite runs its own schema, ``db/sqlite/init.sql`` (the translation of the PostgreSQL
file, which gained an exclusion constraint and a sequence SQLite does not have). A file made by
version 5 is upgraded when it is opened - after checking that no room is already double-booked,
because the rule cannot honestly be switched on over data that breaks it. ``HOTEL_SLOW_STEP`` and
``HOTEL_PORT`` (or ``--slow-step`` / ``--port``) set the experiment's gap and the second
instance's port.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from starlette.applications import Starlette

from hotel_booking.api import UnitOfWork, create_app
from hotel_booking.api_cache import AvailabilityCache, CacheError, InMemoryKeyValueStore, KeyValueStore
from hotel_booking.api_redis import RedisKeyValueStore
from hotel_booking.api_stats import CountingReservationStore, Stats
from hotel_booking.demo import HOTEL_ROOMS, run_demo, run_race
from hotel_booking.notifications import NotificationSender
from hotel_booking.notifications.internal import EmailNotificationSender
from hotel_booking.reservations import BookingService, ReservationStore
from hotel_booking.reservations.internal import InMemoryReservationStore, SqlReservationStore
from hotel_booking.rooms import Room
from hotel_booking.rooms.internal import InMemoryRoomCatalog, SqlRoomCatalog

PROJECT = Path(__file__).resolve().parent
SCHEMA = PROJECT / "db" / "sqlite" / "init.sql"                # what SQLite runs for a new file (P09)
SQLITE_UPGRADE = PROJECT / "db" / "sqlite" / "p09-upgrade.sql"  # version-5 file -> version 6
POSTGRES_SCHEMA = PROJECT / "db" / "postgres" / "init.sql"     # what docker-compose mounts
FIND_DOUBLE_BOOKINGS = PROJECT / "db" / "find-double-bookings.sql"
DEFAULT_SQLITE_PATH = PROJECT / "hotel.sqlite3"
HOST, PORT = "localhost", 5080
RACE_SLOW_STEP_SECONDS = 0.5  # widens the check-then-save gap so the race shows (demo only)

Connect = Callable[[], Any]  # opens a new DB-API 2 connection (sqlite3 or psycopg)
CacheKind = Literal["redis", "memory", "off"]
CACHE_KINDS: tuple[CacheKind, ...] = ("redis", "memory", "off")


@dataclass(frozen=True)
class ServerOptions:
    """What ``python main.py`` was asked to serve."""

    database: str = "sqlite"
    port: int = PORT
    cache: CacheKind = "redis"
    invalidation: bool = True
    slow_step_seconds: float = 0.0  # P09: HOTEL_SLOW_STEP, the widened check-then-save gap


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


class UpgradeRefused(RuntimeError):
    """A version-5 database still holds double bookings, so the no-overlap rule cannot be switched on."""


def sqlite_connector(path: Path) -> Connect:
    """Connections to one SQLite file; the first one creates the tables (db/sqlite/init.sql) or upgrades a v5 file."""
    def connect() -> sqlite3.Connection:
        # timeout: a writer waits up to 5 s for another request's write lock instead of failing.
        return sqlite3.connect(path, timeout=5.0)

    with closing(connect()) as connection:
        tables = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "reservations" not in tables:
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        elif "reservation_ids" not in tables:
            upgrade_sqlite(connection)
    return connect


def upgrade_sqlite(connection: sqlite3.Connection) -> None:
    """Version 5 -> 6: add the no-overlap triggers and the id table, in one transaction.

    Refused, with every offending pair named, while a room has two Confirmed reservations sharing a
    night - the same refusal PostgreSQL gives for ALTER TABLE ... EXCLUDE (P09 Step 7.1). A person
    decides which booking to cancel; the program does not guess.
    """
    pairs = connection.execute(FIND_DOUBLE_BOOKINGS.read_text(encoding="utf-8")).fetchall()
    if pairs:
        listed = "; ".join(f"{first} and {second} both have {room} for {in1}..{out1} / {in2}..{out2}"
                           for first, second, room, in1, out1, in2, out2 in pairs)
        raise UpgradeRefused(f"Cannot switch on reservations_no_overlap: {listed}. "
                             "Cancel one reservation of each pair, then start the app again.")
    try:
        connection.executescript(f"BEGIN;\n{SQLITE_UPGRADE.read_text(encoding='utf-8')}\nCOMMIT;")
    except sqlite3.Error:
        connection.rollback()
        raise


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
    connect: Connect, rooms: list[Room], sender: NotificationSender, slow_step_seconds: float = 0.0,
    stats: Stats | None = None,
) -> UnitOfWork:
    """One request = one connection, one store, one BookingService; save at the end or roll back.

    P08: with ``stats`` the booking service gets the store wrapped in a ``CountingReservationStore``,
    so GET /stats counts every database question; ``save_changes`` is called on the real store.
    """
    @contextmanager
    def unit_of_work() -> Iterator[BookingService]:
        connection = connect()
        try:
            store = SqlReservationStore(connection, rooms)
            counted: ReservationStore = store if stats is None else CountingReservationStore(store, stats)
            yield BookingService(rooms, counted, sender, slow_step_seconds=slow_step_seconds)
            store.save_changes()  # UPDATE what changed, then COMMIT
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    return unit_of_work


def build_api(
    connect: Connect, slow_step_seconds: float = 0.0, sender: NotificationSender | None = None, *,
    cache: AvailabilityCache | None = None, stats: Stats | None = None,
) -> tuple[Starlette, NotificationSender]:
    """The web app over a database: the rooms are read once, the reservations once per request.

    The email sender is the default; tests may hand in another ``NotificationSender``. P08: one
    ``Stats`` is shared by GET /stats and the counting store; ``cache=None`` means no cache.
    """
    with closing(connect()) as connection:
        rooms = SqlRoomCatalog(connection).all()
    sender = sender or EmailNotificationSender()
    stats = stats if stats is not None else Stats()
    app = create_app(rooms, sql_unit_of_work(connect, rooms, sender, slow_step_seconds, stats), stats, cache)
    return app, sender


def build_cache(kind: CacheKind, invalidation: bool = True,
                redis_store: Callable[[], RedisKeyValueStore] | None = None) -> AvailabilityCache | None:
    """The search cache the options ask for; Redis must answer PING, or the app does not start."""
    if kind == "off":
        return None
    store: KeyValueStore
    if kind == "memory":
        store = InMemoryKeyValueStore()
    else:
        redis = (redis_store or redis_from_environment)()
        try:
            redis.ping()  # stop here if Redis is not running: a misconfiguration should be loud
        except CacheError as error:
            raise SystemExit(f"{error}\nStart Redis (docker compose up -d) or choose --cache memory / --cache off.")
        store = redis
    return AvailabilityCache(store, invalidate_on_change=invalidation)


def redis_from_environment() -> RedisKeyValueStore:
    """Redis from docker-compose.yml (HOTEL_REDIS_HOST / HOTEL_REDIS_PORT only if not localhost:6379)."""
    return RedisKeyValueStore(os.getenv("HOTEL_REDIS_HOST", "localhost"), int(os.getenv("HOTEL_REDIS_PORT", "6379")))


def run_api(options: ServerOptions) -> None:  # pragma: no cover - starts a server
    import uvicorn

    if options.database == "postgres":
        connect = postgres_connector(int(os.getenv("HOTEL_DB_PORT", "5432")))
    else:
        connect = sqlite_connector(Path(os.getenv("HOTEL_DB_PATH", str(DEFAULT_SQLITE_PATH))))
    app, _ = build_api(connect, options.slow_step_seconds, cache=build_cache(options.cache, options.invalidation))
    uvicorn.run(app, host=HOST, port=options.port)


# --------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None, serve: Callable[[ServerOptions], None] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Hotel booking app, version 6 (P09: HTTP API + database that keeps the booking rule + search cache).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="print the nine demo lines (data in lists)")
    mode.add_argument("--race", action="store_true",
                      help="run two simultaneous bookings of R7: one is accepted, one refused (data in lists)")
    parser.add_argument("--db", choices=("sqlite", "postgres"), default="sqlite",
                        help="the web app's database (default: sqlite)")
    parser.add_argument("--port", type=int, default=int(os.getenv("HOTEL_PORT", str(PORT))),
                        help=f"the web app's port (default: HOTEL_PORT, else {PORT})")
    parser.add_argument("--slow-step", dest="slow_step_seconds", type=float,
                        default=float(os.getenv("HOTEL_SLOW_STEP", "0")),
                        help="P09 experiment: seconds every booking waits between its check and its save "
                             "(default: HOTEL_SLOW_STEP, else 0)")
    parser.add_argument("--cache", choices=CACHE_KINDS, default="redis",
                        help="the search cache: redis (default, docker compose), memory (this process only) or off")
    parser.add_argument("--no-invalidation", dest="invalidation", action="store_false",
                        help="P08 Step 5 experiment only: bookings and cancels do not invalidate the cache")
    args = parser.parse_args(argv)
    if args.race:
        service, store, _ = build_app(slow_step_seconds=RACE_SLOW_STEP_SECONDS)
        run_race(service, store)
    elif args.demo:
        service, _, email = build_app()
        run_demo(service, lambda: email.sent)
    else:
        (serve or run_api)(ServerOptions(args.db, args.port, args.cache, args.invalidation, args.slow_step_seconds))


if __name__ == "__main__":
    main()
