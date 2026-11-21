# hotel-booking

The course project of *Advanced Software Design & Architecture*: a small fictional hotel (rooms R7
and R8) that takes bookings on its website and at the reception desk. This folder is **one growing
codebase**; each practice evolves it and keeps earlier behaviour (and tests) working.

| Version | Practice | What it adds |
|---|---|---|
| 1 | [P03](../practices/P03-hotel-domain-uml/README.md) | Domain classes and the booking workflow from the P03 UML; in memory; demo + race demo |
| 2 | [P04](../practices/P04-refactor-reservation/README.md) | SOLID refactor, same behaviour: `BookingService` depends only on the `ReservationStore` and `NotificationSender` protocols; `main.py` is the composition root; 8 `unittest` tests. New after the refactor: R6 (a failed confirmation keeps the booking) and `SmsNotificationSender` |
| — | [P05](../practices/P05-domain-context-boundaries/README.md) | Design only: quality scenarios, four bounded contexts, rule owners, context map (docs copied into `docs/` in P06) |
| 3 | [P06](../practices/P06-modular-monolith-review/README.md) | **Modular monolith**, same behaviour: four modules (rooms, reservations, payments, notifications), each a package with a public contract and `internal.py`; Notifications gets its own `Confirmation` message; Payments contract + simulated service; `main.py` is the only app file that names internal code; the borders are checked (`.importlinter` + `tests/test_architecture.py`); ADR-001 |
| 4 | [P07](../practices/P07-capacity-api-design/README.md) | **HTTP API + database**, same booking rule: capacity estimate (`docs/capacity.md`, `capacity.py`); hand-written contract `docs/openapi.yaml` checked against the code both ways; `hotel_booking/api.py` (Starlette + pydantic, uvicorn on :5080) with problem-details errors and cursor paging; `SqlReservationStore` / `SqlRoomCatalog` behind the same promises, a unit of work per request; SQLite by default, the same `db/postgres/init.sql` for PostgreSQL in `docker-compose.yml`; `docs/api-check.md` run against the real server |
| 5 | [P08](../practices/P08-cache-scale-experiment/README.md) | **Measured, then cached**, same booking rule: `GET /stats` (searches, database queries, cache hits/misses/errors) with a counting store around the SQL store; `tools/measure.py` (1,000 searches: average, p95, counters); cache-aside for the search only in Redis (`hotel_booking/api_cache.py` + `api_redis.py`, key `availability:v{version}:{checkIn}:{checkOut}`, TTL 30 s, version raised after every committed booking/cancel, fail-open); contract 1.1.0; `docs/cache-experiment.md` (real runs) and ADR-002 |

Planned by the course (not implemented yet): P09 concurrency fix for the race, P10 asynchronous notifications, P11 idempotency key for
`POST /reservations`, P17 booking saga with the Payments deposit.

## Requirements

- Python 3.12 or newer (developed and tested on 3.13).
- From P07 the app has runtime dependencies: `starlette`, `pydantic`, `uvicorn` (the web app);
  optional `psycopg[binary]` for PostgreSQL. Tests and tools: `pytest`, `httpx2` (Starlette's
  TestClient), `PyYAML` + `jsonschema` (contract test), `mypy`, `import-linter`. All in `requirements.txt`.
- PostgreSQL is optional: SQLite (standard library) is the default database. For PostgreSQL:
  Docker Desktop, `docker compose up -d`, then `python main.py --db postgres`.
- From P08 the web app uses **Redis** for the search cache by default (`docker compose up -d` starts
  `redis:8` on port 6379; `HOTEL_REDIS_HOST`/`HOTEL_REDIS_PORT` change the address). No Python
  package is needed for it: `hotel_booking/api_redis.py` speaks Redis's protocol with the standard
  library. Without Redis: `python main.py --cache memory` or `--cache off`.

```bash
cd hotel-booking
python3 -m venv .venv && source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py                      # the HTTP API on http://localhost:5080, reservations in hotel.sqlite3,
                                    #   search cache in Redis (docker compose up -d first)
python main.py --db postgres        # the same API on PostgreSQL (docker compose up -d first; needs psycopg)
python main.py --cache memory       # P08: the cache inside this process (no Redis; one instance only)
python main.py --cache off          # P08: no cache - every search asks the database ("No cache" row)
python main.py --no-invalidation    # P08 Step 5 experiment only: shows the stale result
python tools/measure.py             # P08, second terminal: 1,000 searches -> average, p95, GET /stats difference
python tools/measure.py 2026-12-31 2027-01-02 --clients 8   # other dates, 8 clients at once
python main.py --demo               # the console demo: nine lines proving R1-R4 (data in lists)
python main.py --race               # two guests book R7 for the same nights at the same moment
python capacity.py                  # the capacity estimate, line by line (docs/capacity.md)
python -m unittest -v               # the course's 14 tests: 8 behaviour (test_booking_service.py) + 6 API (test_api.py)
lint-imports                        # the 6 borders in .importlinter (needs import-linter)
python -m tests.test_architecture   # the same 6 borders, standard library only, lint-imports-style output
python -m pytest                    # everything: unittest tests + the pytest suite in tests/
python -m mypy                      # strict type check, incl. that every class keeps its protocol
```

With the API running, `docs/api-check.md` lists every request (curl) and its exact answer; the
contract is served at http://localhost:5080/openapi.yaml and the counters at http://localhost:5080/stats.
`docs/cache-experiment.md` has the measurements (with and without the cache), the stale result
and the hot key; `docs/adr-002-cache-availability.md` the decision.

Expected demo output (`--demo`; identical in versions 1 to 5):

```text
Free rooms 12-14 Nov: R7, R8
Maya books R7 12-14 Nov: Accepted R101
Omar books R7 13-15 Nov: Unavailable
Nora books R7 14-16 Nov: Accepted R102
Omar books R8 15-15 Nov: InvalidDates
Free rooms 12-14 Nov: R8
Maya cancels R101: True
Free rooms 12-14 Nov: R7, R8
Confirmation emails sent: 2
```

Expected race output (a **known defect**, kept on purpose until P09 — a refactoring does not fix bugs):

```text
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

Expected border check:

```text
Reservations uses only the public contracts of other modules KEPT
Rooms does not depend on any other module KEPT
Payments and Notifications do not depend on Reservations KEPT
The HTTP API uses only the public contracts of the modules KEPT
No module depends on the HTTP API KEPT
The availability cache depends on no module KEPT

Contracts: 6 kept, 0 broken.
```

## Layout

```text
hotel-booking/
├── main.py                     wiring: the only app file that names internal code; web app (default), --demo, --race
├── capacity.py                 P07: the capacity estimate as a program (docs/capacity.md is checked against it)
├── tools/measure.py            P08: N searches against the running app -> average, p50/p95/p99, total, GET /stats difference
├── test_booking_service.py     the course's 8 unittest tests (P04) + FakeNotificationSender (receives a Confirmation)
├── test_api.py                 P07/P08: the course's 6 API tests (Starlette TestClient, list store, cache in a dictionary)
├── .importlinter               the 3 module borders (P06) + 2 API borders (P07, now covering the 4 edge files) + 1 cache border (P08)
├── docker-compose.yml          P07/P08: PostgreSQL 18 (mounts db/postgres/init.sql) + Redis 8 (no volume) for the Mac
├── db/postgres/init.sql        P07: rooms + reservations tables (portable: SQLite runs the same file)
├── hotel_booking/
│   ├── __init__.py             docstring only - re-exports nothing
│   ├── api.py                  P07: the HTTP edge (Starlette + pydantic): 3 operations + GET /openapi.yaml, problem details;
│   │                           P08: GET /stats, cache-aside search (X-Cache header), invalidation after commit
│   ├── api_stats.py            P08: Stats (the counters, thread-safe) and CountingReservationStore (decorator)
│   ├── api_cache.py            P08: KeyValueStore promise, AvailabilityCache (key, TTL, version), InMemoryKeyValueStore
│   ├── api_redis.py            P08: RedisKeyValueStore - RESP2 over a socket, pooled, 0.5 s timeout (stdlib only)
│   ├── rooms/                  Rooms: __init__.py (contract: Room, RoomCatalog), catalog.py, internal.py (InMemoryRoomCatalog, SqlRoomCatalog)
│   ├── reservations/           Reservations: __init__.py (contract), domain.py (DateRange, Guest, Reservation, ReservationStatus),
│   │                           booking.py (ReservationStore, BookingOutcome, BookingResult, BookingService),
│   │                           internal.py (InMemoryReservationStore, SqlReservationStore)
│   ├── payments/               Payments: __init__.py (contract: PaymentStatus, PaymentService), internal.py (SimulatedPaymentService)
│   ├── notifications/          Notifications: __init__.py (contract: Confirmation, NotificationSender), internal.py (Email/Sms senders)
│   └── demo.py                 the classroom scenario (R7, R8, Maya, Omar, Nora) and the race; uses contracts only
├── tests/                      pytest suite (P03 on; every deliberate change noted in the module docstring)
│   ├── test_domain.py          DateRange half-open rule, Reservation status/encapsulation
│   ├── test_booking_service.py R1-R5 and the R3 invariant (one request at a time)
│   ├── test_sequences.py       message order of each sequence diagram, via spies (+ R6)
│   ├── test_demo_and_race.py   exact demo output; race known defect + control case
│   ├── test_uml_conformance.py code == P07 class diagram (classes, members, interfaces, links, modules)
│   ├── test_dependency_rule.py P04: booking.py names no concrete helper; only main.py creates them (not the API)
│   ├── test_substitution.py    P04: any sender/store that keeps the promise gives the same records
│   ├── test_modules.py         P06: Rooms catalog, Payments deposit, the Confirmation translation
│   ├── test_architecture.py    P06/P07: the 5 border contracts (ast import graph) + extras + self-tests
│   ├── test_api_http.py        P07: every success and error path over HTTP, idempotency, 404/405/500
│   ├── test_openapi_contract.py P07: docs/openapi.yaml == the implemented API, both directions; examples executed
│   ├── test_sql_store.py       P07: list and SQL store keep the same promise; unit of work; schema; queries per search
│   ├── test_api_sqlite.py      P07: api-check + restart through the real wiring on SQLite; the race over HTTP
│   ├── test_capacity.py        P07: capacity.md numbers == capacity.py; peak == l04-notes
│   ├── test_cache.py           P08: key, value, TTL expiry (fake clock), version, in-memory store
│   ├── test_api_cache.py       P08: hit/miss/expiry/invalidation over HTTP, stale result pinned, fail-open, "booking never reads the cache" (ast)
│   ├── test_redis_store.py     P08: RESP2 wire format; GET/SET EX/INCR/expiry/outage on a real redis-server
│   ├── test_cache_wiring.py    P08: Steps 5 and 6 through main.build_api on SQLite + real Redis; SQL statements counted; CLI flags
│   └── test_measure.py         P08: tools/measure.py against a real uvicorn server; nearest-rank p95
├── docs/
│   ├── requirements.md         R1-R6 with Check and Proof lines, invariant
│   ├── design-notes.md         P03, P04, P06 and P07 sections
│   ├── quality-scenarios.md    P05: stakeholders and S1-S6
│   ├── contexts.md             P05: words, four contexts, rule owners, context map, borders (+ P06 status)
│   ├── adr-001-modular-monolith.md   P06: why one program with four modules
│   ├── capacity.md             P07: assumptions, results, checked by hand, what to measure (answered in P08)
│   ├── cache-experiment.md     P08: measurements with and without the cache (real runs), stale result, invalidation, hot key, Redis outage
│   ├── adr-002-cache-availability.md  P08: why the search (only) is cached in Redis, TTL 30 s + version
│   ├── openapi.yaml            P07: the API contract (OpenAPI 3.1), served at GET /openapi.yaml
│   ├── api-check.md            P07: every request with curl and its exact answer; SQLite run observed
│   ├── requests/               P07: request bodies for curl (maya-r7, omar-r7, omar-r8 + three error bodies); P08: maya-newyear
│   ├── diagrams.drawio         pages "Context map" (P05) and "Modules" (P06)
│   └── l02-notes.md, l03-notes.md, l04-notes.md   lecture exit-check answers
├── pyproject.toml              pytest / mypy configuration, dependencies
└── requirements.txt
```

## Design in one paragraph

The app is one program with four modules behind an HTTP edge (P07). **Reservations** owns the booking rule:
`BookingService.reserve` validates the stay (`DateRange.is_valid`), asks its store `has_overlap`,
then creates a `Reservation`, saves it, translates it into Notifications' own `Confirmation`
(reservation id, guest email, room number, check-in, check-out) and hands that to a
`NotificationSender`; a failed send keeps the booking (`notification_failed=True`, R6). It knows
the other modules only through their contracts: `Room` from **Rooms** (the wiring passes
`InMemoryRoomCatalog.all()` in), `NotificationSender`/`Confirmation` from **Notifications**, and —
from P17 — `PaymentService` from **Payments**. Rooms, Payments and Notifications never import
Reservations, so no dependency circle can form. `main.py` is the only application file that names
internal classes. The borders are not a convention: `tests/test_architecture.py` parses every
import with `ast` and fails on any import the three contracts in `.importlinter` forbid (directly or
through other modules). UML and code are kept identical by `tests/test_uml_conformance.py`
against `practices/P07-capacity-api-design/diagrams/class-diagram.mmd`.

**P07:** `hotel_booking/api.py` turns HTTP into exactly one `BookingService` call per request and
the answer back into a status code (201/409/400, 200, 204/404; any error as RFC 9457 problem
details). It knows only the public contracts and a *unit of work* handed in by the wiring: for each
request `main.py` opens a database connection, builds a `SqlReservationStore` and a
`BookingService` over it, and at the end writes the changed statuses and commits (or rolls back).
The SQL store keeps the same promise as the list store (one shared test suite runs against both);
`BookingService` did not change. `docs/openapi.yaml` was written first and
`tests/test_openapi_contract.py` keeps code and contract equal in both directions.

**P08:** the search is measured and cached; the booking rule did not move. The wiring wraps the SQL
store in a `CountingReservationStore` (same promise, counts each database question for
`GET /stats`). The search endpoint does cache-aside (`search_free_rooms`): it builds the key
`availability:v{version}:{checkIn}:{checkOut}`, answers a hit from the copy without opening a unit of
work, and on a miss asks the database and keeps the room numbers for 30 s. `POST` and `DELETE` never
read the cache; after their unit of work has committed a 201/204 they raise `availability:version`.
The cache lives at the edge (`api_cache.py`, `api_redis.py`), imports no module, and a failing cache
never fails a request (the search falls back to the database, `cacheErrors` counts it).

## Known limitations of version 5

- **Race condition (R3/S2 under concurrency):** check (`has_overlap`) and act (`save`) are still
  separate steps. In memory: pinned by `test_race_double_books_r7_known_defect`. Through HTTP and
  SQLite: two simultaneous bookings either both succeed (R101 + R102, double booking) or, when both
  number theirs R101, the primary key refuses the second with 500 InternalError — pinned by
  `test_race_through_the_database_still_double_books_known_defect` and
  `test_two_requests_numbering_r101_the_primary_key_refuses_the_second`. Fixed in P09.
- **POST is not idempotent:** a retried booking answers 409 for the guest's own stay and the client
  never learns its id (pinned by `test_post_is_not_idempotent_…`; Idempotency-Key in P11).
- Reservation ids come from the row count (`R{101 + count}`): fine for one writer, the source of the
  R101 clash for several (P09).
- **Cache trade-offs (P08, ADR-002):** a search may show a booked room for a moment (between the
  commit and the version INCR, or up to 30 s if the INCR fails); several simultaneous misses all
  ask the database (stampede: 8 clients → 8 misses, measured); one New Year key takes nearly all
  searches (hot key); every booking empties all cached searches. Booking never reads the cache, so
  none of this can cause a double booking.
- The measurements ran on SQLite in a Linux container with Redis 7 on localhost; the PostgreSQL +
  Docker run on the Mac is to do (docs/cache-experiment.md, Limitations).
- `cacheErrors` and the log are the only signal of a Redis outage (fail-open hides it from guests);
  no alerting yet.
- The PostgreSQL path (`--db postgres`, psycopg) was not run in the build container (no driver,
  no Docker daemon); its SQL was run on PostgreSQL 16 with psql. To run on the student's Mac.
- The confirmation is sent before the commit: if the commit then fails, the guest has an email for
  a booking that was rolled back (P10 moves sending after the commit / to a queue).
- The demo pause `slow_step_seconds` still sits inside `reserve()` (0 in normal use).
- R6 reports a failed confirmation but nothing resends it yet (P10).
- Python cannot *hide* internal code: `internal.py` is a naming convention, and the border holds
  only because the architecture tests run with every test run (CI from P25).
- Payments exists but is not called; the 30% deposit rule arrives with P17.
- No authentication: anyone who can reach the port can cancel any reservation (S4, P21).
