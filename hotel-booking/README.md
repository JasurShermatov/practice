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
| 6 | [P09](../practices/P09-protect-the-last-seat/README.md) | **The last seat protected** - the race of P03-P08 fixed: `ReservationStore.save` now *promises* to refuse a double booking (`OverlapRejected`, answered 409 Unavailable) and the store hands out ids (`next_reservation_id`). PostgreSQL keeps the rule with the exclusion constraint `reservations_no_overlap` (btree_gist) and a sequence; SQLite with triggers of the same name and a one-row id table (`db/sqlite/init.sql`); the list store with a lock. `tools/race_http.py`, `HOTEL_SLOW_STEP`/`HOTEL_PORT`; upgrade scripts for version-5 databases; contract 1.2.0; `docs/interleaving.md`, ADR-003 |
| 7 | [P10](../practices/P10-bounded-async-processing/README.md) | **Confirmations from a bounded queue** - the email left the booking request: `QueuedNotificationSender` (bounded queue, default 10; a fixed number of worker threads, default 1; a full queue *refuses and counts*, never waits; retry policy `HOTEL_SEND_ATTEMPTS` (default 1 = no retry); the sender's own timeout; `close()` stops accepting, drains with a time limit and names every guest still owed); `HeldConfirmations` holds a place inside the transaction and hands the email over only after COMMIT (a refusal answers `notificationFailed: true`, a rollback is never emailed); counters + `DeliveryStatus` in the Notifications contract; GET /stats + 5 optional counters; shutdown hook (Ctrl+C and SIGTERM drain); `HOTEL_EMAIL_SECONDS`, `HOTEL_QUEUE_CAPACITY`, `HOTEL_WORKERS`, `--no-queue`, `--no-drain`; `tools/burst.py`; contract 1.3.0; 7 border contracts + "only the queue starts threads"; `docs/queue-trace.md`, ADR-004 |

Planned by the course (not implemented yet): P11 idempotency key for
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
python main.py --race               # two guests book R7 for the same nights at the same moment: one gets it (P09)
HOTEL_SLOW_STEP=1 python main.py    # P09: every booking waits 1 s between check and save (the race is easy to hit)
HOTEL_SLOW_STEP=1 HOTEL_PORT=5081 python main.py   # P09 Step 4: a second instance on the same database
python tools/race_http.py           # P09: two bookings for R7 at the same moment -> one 201, one 409
HOTEL_EMAIL_SECONDS=1 python main.py           # P10: a one-second mail server; the booking does not wait for it
HOTEL_EMAIL_SECONDS=1 python main.py --no-queue   # P10 "before": the email is sent inside the request again
HOTEL_EMAIL_SECONDS=1 HOTEL_QUEUE_CAPACITY=10000 python main.py   # P10 Step 3: a queue that never refuses
python tools/burst.py               # P10, second terminal: 30 bookings, then GET /stats (queue counters)
python tools/burst.py --wait        # ... and wait for the workers: drain time and emails per second
HOTEL_WORKERS=3 HOTEL_SEND_ATTEMPTS=3 HOTEL_DRAIN_SECONDS=30 python main.py   # P10: workers, retry, drain limit
python tools/race_http.py http://localhost:5081 --repeat 20   # Omar to the second instance, 20 rounds
python capacity.py                  # the capacity estimate, line by line (docs/capacity.md)
python -m unittest -v               # the course's 19 tests: 8 behaviour (test_booking_service.py) + 11 API/queue (test_api.py)
lint-imports                        # the 7 borders in .importlinter (needs import-linter)
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

Expected race output (since P09; versions 1 to 5 printed "Omar: Accepted R102" and "Double booking!"):

```text
Maya and Omar both book R7 for 12-14 Nov at the same moment...
Maya: Accepted R101
Omar: Unavailable
Confirmed reservations for R7 on 12-14 Nov: 1
Only one guest has R7.
```

Expected race tool output (`HOTEL_SLOW_STEP=1 python main.py`, then `python tools/race_http.py`):

```text
Two bookings for R7, 2026-11-12 to 2026-11-14, sent at the same moment.

Maya -> 201 Created   {"id":"R101","status":"Confirmed","notificationFailed":false}
Omar -> 409 Conflict  {"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}

Confirmed reservations for R7 on 12-14 Nov: 1
CORRECT: one booking was accepted and one was refused.
```

A PostgreSQL database created by version 5 needs the P09 changes once (init.sql runs only when the
database is created): `docker compose exec -T db psql -U hotel -d hotel -v ON_ERROR_STOP=1 < db/postgres/p09-upgrade.sql`.
It is refused while a room still has two Confirmed reservations for one night -
`db/find-double-bookings.sql` lists them; cancel one of each pair first. A version-5 SQLite file is
upgraded by `main.py` itself when it is opened, with the same refusal.

Expected border check:

```text
Reservations uses only the public contracts of other modules KEPT
Rooms does not depend on any other module KEPT
Payments and Notifications do not depend on Reservations KEPT
The HTTP API uses only the public contracts of the modules KEPT
No module depends on the HTTP API KEPT
The availability cache depends on no module KEPT
Notifications depends on no other module KEPT

Contracts: 7 kept, 0 broken.
```

## Layout

```text
hotel-booking/
├── main.py                     wiring: the only app file that names internal code; web app (default), --demo, --race
├── capacity.py                 P07: the capacity estimate as a program (docs/capacity.md is checked against it)
├── tools/measure.py            P08: N searches against the running app -> average, p50/p95/p99, total, GET /stats difference
├── tools/race_http.py          P09: two bookings for R7 at the same moment (Omar optionally to a second instance); --repeat
├── tools/burst.py              P10: N bookings one after another, then GET /stats; --wait: drain time + worker throughput
├── test_booking_service.py     the course's 8 unittest tests (P04) + FakeNotificationSender (receives a Confirmation)
├── test_api.py                 P07/P08/P09: the course's 8 API tests (Starlette TestClient, list store, cache in a dictionary)
├── .importlinter               the 3 module borders (P06) + 2 API borders (P07, now covering the 4 edge files) + 1 cache border (P08)
├── docker-compose.yml          P07/P08: PostgreSQL 18 (mounts db/postgres/init.sql) + Redis 8 (no volume) for the Mac
├── db/postgres/init.sql        P07: rooms + reservations tables; P09: + btree_gist, EXCLUDE reservations_no_overlap, SEQUENCE reservation_ids
├── db/postgres/p09-upgrade.sql P09: the same for a database created by version 5 (one transaction; refused over double bookings)
├── db/sqlite/init.sql          P09: SQLite's translation (same tables; triggers reservations_no_overlap_*; one-row reservation_ids)
├── db/sqlite/p09-upgrade.sql   P09: version-5 SQLite file -> 6 (main.py runs it after checking for double bookings)
├── db/find-double-bookings.sql P09: every pair of Confirmed reservations sharing a night (portable)
├── hotel_booking/
│   ├── __init__.py             docstring only - re-exports nothing
│   ├── api.py                  P07: the HTTP edge (Starlette + pydantic): 3 operations + GET /openapi.yaml, problem details;
│   │                           P08: GET /stats, cache-aside search (X-Cache header), invalidation after commit
│   ├── api_stats.py            P08: Stats (the counters, thread-safe) and CountingReservationStore (decorator)
│   ├── api_cache.py            P08: KeyValueStore promise, AvailabilityCache (key, TTL, version), InMemoryKeyValueStore
│   ├── api_redis.py            P08: RedisKeyValueStore - RESP2 over a socket, pooled, 0.5 s timeout (stdlib only)
│   ├── rooms/                  Rooms: __init__.py (contract: Room, RoomCatalog), catalog.py, internal.py (InMemoryRoomCatalog, SqlRoomCatalog)
│   ├── reservations/           Reservations: __init__.py (contract), domain.py (DateRange, Guest, Reservation, ReservationStatus),
│   │                           booking.py (ReservationStore, OverlapRejected, BookingOutcome, BookingResult, BookingService),
│   │                           internal.py (InMemoryReservationStore, SqlReservationStore, is_overlap_refusal)
│   ├── payments/               Payments: __init__.py (contract: PaymentStatus, PaymentService), internal.py (SimulatedPaymentService)
│   ├── notifications/          Notifications: __init__.py (contract: Confirmation, NotificationSender; P10: NotificationCounts,
│   │                           DeliveryStatus, ConfirmationRefused), internal.py (Email/Sms senders; P10: QueuedNotificationSender -
│   │                           the bounded queue and the app's only threads -, HeldConfirmations, ShutdownReport)
│   └── demo.py                 the classroom scenario (R7, R8, Maya, Omar, Nora) and the race; uses contracts only
├── tests/                      pytest suite (P03 on; every deliberate change noted in the module docstring)
│   ├── test_domain.py          DateRange half-open rule, Reservation status/encapsulation
│   ├── test_booking_service.py R1-R5 and the R3 invariant (one request at a time)
│   ├── test_sequences.py       message order of each sequence diagram, via spies (+ R6)
│   ├── test_demo_and_race.py   exact demo output; race regression (one guest gets R7; P09) + control case
│   ├── test_concurrency.py     P09: the store's no-overlap promise and ids (both stores), 50 threads / 8 SQLite connections, PostgreSQL path
│   ├── test_uml_conformance.py code == P07 class diagram (classes, members, interfaces, links, modules)
│   ├── test_dependency_rule.py P04: booking.py names no concrete helper; only main.py creates them (not the API)
│   ├── test_substitution.py    P04: any sender/store that keeps the promise gives the same records
│   ├── test_modules.py         P06: Rooms catalog, Payments deposit, the Confirmation translation
│   ├── test_architecture.py    P06/P07: the 5 border contracts (ast import graph) + extras + self-tests
│   ├── test_api_http.py        P07: every success and error path over HTTP, idempotency, 404/405/500
│   ├── test_openapi_contract.py P07: docs/openapi.yaml == the implemented API, both directions; examples executed
│   ├── test_sql_store.py       P07: list and SQL store keep the same promise; unit of work; schema; queries per search
│   ├── test_api_sqlite.py      P07: api-check + restart through the real wiring on SQLite; P09: the race over HTTP = one 201 + one 409
│   ├── test_capacity.py        P07: capacity.md numbers == capacity.py; peak == l04-notes
│   ├── test_cache.py           P08: key, value, TTL expiry (fake clock), version, in-memory store
│   ├── test_api_cache.py       P08: hit/miss/expiry/invalidation over HTTP, stale result pinned, fail-open, "booking never reads the cache" (ast)
│   ├── test_redis_store.py     P08: RESP2 wire format; GET/SET EX/INCR/expiry/outage on a real redis-server
│   ├── test_cache_wiring.py    P08: Steps 5 and 6 through main.build_api on SQLite + real Redis; SQL statements counted; CLI flags
│   ├── test_measure.py         P08: tools/measure.py against a real uvicorn server; nearest-rank p95
│   ├── test_notification_queue.py P10: bound, backpressure, workers, retry, timeout, no duplicates, drain/cancel, status
│   ├── test_queue_wiring.py    P10: through main.build_api: no wait, 201 when full/failing, after-commit, race, shutdown, real process
│   └── test_burst.py           P10: tools/burst.py against a real uvicorn server with a queue
├── docs/
│   ├── requirements.md         R1-R6 with Check and Proof lines, invariant
│   ├── design-notes.md         P03, P04, P06 and P07 sections
│   ├── quality-scenarios.md    P05: stakeholders and S1-S6
│   ├── contexts.md             P05: words, four contexts, rule owners, context map, borders (+ P06 status)
│   ├── adr-001-modular-monolith.md   P06: why one program with four modules
│   ├── capacity.md             P07: assumptions, results, checked by hand, what to measure (answered in P08)
│   ├── cache-experiment.md     P08: measurements with and without the cache (real runs), stale result, invalidation, hot key, Redis outage
│   ├── adr-002-cache-availability.md  P08: why the search (only) is cached in Redis, TTL 30 s + version
│   ├── interleaving.md         P09: the race traced statement by statement; the four repairs and what each cost (measured)
│   ├── adr-003-booking-concurrency.md P09: why the rule lives in the database (exclusion constraint), alternatives with costs
│   ├── queue-trace.md          P10: the email measured inside the request, on a queue, unbounded, bounded, at shutdown; what it still loses
│   ├── adr-004-notification-concurrency.md P10: a bounded queue with fixed workers; five rejected shapes; the accepted loss
│   ├── openapi.yaml            P07: the API contract (OpenAPI 3.1), served at GET /openapi.yaml
│   ├── api-check.md            P07: every request with curl and its exact answer; SQLite run observed
│   ├── requests/               P07: request bodies for curl (maya-r7, omar-r7, omar-r8 + three error bodies); P08: maya-newyear
│   ├── diagrams.drawio         pages "Context map" (P05) and "Modules" (P06)
│   └── l02-notes.md … l05-notes.md   lecture exit-check answers
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

**P09:** the booking rule is kept by the database, not by the order of two statements. The
pre-check in `reserve` stays (it answers the ordinary case with a readable 409), but the
`ReservationStore` promise now includes "``save`` refuses a reservation that would give the room two
Confirmed reservations for one night" (`OverlapRejected`), and `reserve` answers that refusal with the
same Unavailable. Each store keeps the promise its own way: the PostgreSQL schema has the exclusion
constraint `reservations_no_overlap` (checked by a GiST index as the row goes in, whatever the other
transactions are doing); SQLite has two triggers of the same name (safe there because SQLite has one
writer at a time - the same trigger in PostgreSQL let a double booking through, observed); the list
store checks under a lock. The SQL store recognises only that one refusal (SQLSTATE 23P01 + the
constraint name, or SQLite's trigger error + the name) and re-raises everything else; on PostgreSQL
the INSERT runs in a savepoint so the refused statement does not poison the transaction. Ids come
from the store: `nextval('reservation_ids')`, SQLite's one-row counter, or the list's counter.
`docs/interleaving.md` has the trace and the measured cost of the four repairs, ADR-003 the decision.

**P10:** the confirmation email no longer runs inside the booking request. `BookingService` did not
change - it still calls `send_confirmation` once, after the save. The wiring decides what that call
does: each request gets a `HeldConfirmations`, which only *holds a place* in the process's one
`QueuedNotificationSender` (no waiting; a full or closing queue raises `ConfirmationRefused`, which R6
turns into `notificationFailed: true` with the booking kept). After `save_changes` has committed, the
unit of work publishes the held confirmation to the queue; a rollback gives the place back. A fixed
pool of worker threads (owned by the queue, started by the wiring, stopped by the shutdown hook) sends
the emails, retries as `HOTEL_SEND_ATTEMPTS` allows, and records each outcome (`DeliveryStatus`,
counters on GET /stats, a log line for every refusal, failure and drop). `docs/queue-trace.md` has the
measurements, ADR-004 the decision.

## Known limitations of version 7

- **The queue is in memory (P10, ADR-004).** A polite stop (Ctrl+C, SIGTERM, a normal deploy) drains
  it for up to `HOTEL_DRAIN_SECONDS` and names anyone still owed; `kill -9`, a crash or a power cut
  loses every queued confirmation and nothing records it. The reservations survive (they are in the
  database), the jobs do not. Fix: the transactional outbox (P17).
- **Under a burst some guests get a room and no email** - by design, counted (`notificationsRejected`)
  and visible in the answer (`notificationFailed: true`), but nothing resends it later.
- **Retries are in memory and in the worker:** a retried email holds its worker (the bound does not
  grow), and a send that timed out may in truth have reached the mail server, so a retry can make a
  duplicate *at the mail server* (the queue itself never sends a job twice). Default: no retry.
- **A send in progress cannot be interrupted** (Python threads cannot be stopped); it is bounded by
  the sender's timeout (`HOTEL_EMAIL_TIMEOUT`), and a worker still busy after the join limit is
  reported, not waited for.
- **Every instance has its own queue and counters** (two instances = two bounds, two sets of numbers).
- Under a burst the server log shows one warning with a traceback per refused confirmation (R6's log
  line in `BookingService`, unchanged on purpose: Reservations did not change in P10).

- **Fixed in P09 (was the main limitation of versions 1-5):** the race on the last seat. Check and
  save are still two steps, but the store's `save` refuses a double booking - PostgreSQL by the
  exclusion constraint, SQLite by its triggers, the list store under its lock - and the loser gets
  409. Ids come from the database, so the duplicate-R101 500 is gone too. Kept true by the
  regression tests `test_race_gives_r7_to_exactly_one_guest_regression`,
  `test_race_through_the_database_gives_the_room_to_one_guest`,
  `test_a_booking_made_while_another_is_uncommitted_gets_its_own_id_and_a_409`, the course's two
  P09 tests in `test_api.py` and `tests/test_concurrency.py`.
- **The rule covers one table only.** A rule that spans tables (P17: a booking and its deposit) will
  need a guard-row lock or Serializable (ADR-003, "When to revisit").
- **Ids can have gaps** (a refused booking uses up its number, like any sequence): R101, R103 ... is
  normal, not lost data.
- **Fixed in P10:** SQLite held its write lock while the confirmation was sent inside the
  transaction; the email is now handed over after the COMMIT, so a slow mail server no longer holds
  the lock (still true with `--no-queue`, which exists only for the "before" measurement).
- **The PostgreSQL path ran through a stand-in driver:** psycopg cannot be installed in the build
  container; the app's own SQL store ran against a real PostgreSQL 16 through a small stdlib protocol
  client (`practices/P09-…/evidence/pg_wire.py`). With psycopg on the Mac: to do by the student.
- **POST is not idempotent:** a retried booking answers 409 for the guest's own stay and the client
  never learns its id (pinned by `test_post_is_not_idempotent_…`; Idempotency-Key in P11).
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
- **Fixed in P10:** the confirmation was sent before the commit. It is now published only after a
  successful COMMIT; a rolled-back booking is never emailed (`test_a_booking_that_rolls_back_is_never_emailed`).
- The experiment pause `slow_step_seconds` still sits inside `reserve()` (0 in normal use; `HOTEL_SLOW_STEP`).
- R6 reports a failed confirmation; since P10 the queue can retry (`HOTEL_SEND_ATTEMPTS`), but a
  confirmation that finally failed or was refused is only counted and logged, not resent later (P17).
- Python cannot *hide* internal code: `internal.py` is a naming convention, and the border holds
  only because the architecture tests run with every test run (CI from P25).
- Payments exists but is not called; the 30% deposit rule arrives with P17.
- No authentication: anyone who can reach the port can cancel any reservation (S4, P21).
