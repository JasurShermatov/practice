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

Planned by the course (not implemented yet): P08 cache for the search (and its measurement), P09
concurrency fix for the race, P10 asynchronous notifications, P11 idempotency key for
`POST /reservations`, P17 booking saga with the Payments deposit.

## Requirements

- Python 3.12 or newer (developed and tested on 3.13).
- From P07 the app has runtime dependencies: `starlette`, `pydantic`, `uvicorn` (the web app);
  optional `psycopg[binary]` for PostgreSQL. Tests and tools: `pytest`, `httpx2` (Starlette's
  TestClient), `PyYAML` + `jsonschema` (contract test), `mypy`, `import-linter`. All in `requirements.txt`.
- PostgreSQL is optional: SQLite (standard library) is the default database. For PostgreSQL:
  Docker Desktop, `docker compose up -d`, then `python main.py --db postgres`.

```bash
cd hotel-booking
python3 -m venv .venv && source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py                      # the HTTP API on http://localhost:5080, reservations in hotel.sqlite3
python main.py --db postgres        # the same API on PostgreSQL (docker compose up -d first; needs psycopg)
python main.py --demo               # the console demo: nine lines proving R1-R4 (data in lists)
python main.py --race               # two guests book R7 for the same nights at the same moment
python capacity.py                  # the capacity estimate, line by line (docs/capacity.md)
python -m unittest -v               # the course's 12 tests: 8 behaviour (test_booking_service.py) + 4 API (test_api.py)
lint-imports                        # the 5 borders in .importlinter (needs import-linter)
python -m tests.test_architecture   # the same 5 borders, standard library only, lint-imports-style output
python -m pytest                    # everything: unittest tests + the pytest suite in tests/
python -m mypy                      # strict type check, incl. that every class keeps its protocol
```

With the API running, `docs/api-check.md` lists every request (curl) and its exact answer; the
contract is served at http://localhost:5080/openapi.yaml.

Expected demo output (`--demo`; identical in versions 1 to 4):

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

Contracts: 5 kept, 0 broken.
```

## Layout

```text
hotel-booking/
├── main.py                     wiring: the only app file that names internal code; web app (default), --demo, --race
├── capacity.py                 P07: the capacity estimate as a program (docs/capacity.md is checked against it)
├── test_booking_service.py     the course's 8 unittest tests (P04) + FakeNotificationSender (receives a Confirmation)
├── test_api.py                 P07: the course's 4 API tests (Starlette TestClient, list store)
├── .importlinter               the 3 module borders (P06) + 2 API borders (P07)
├── docker-compose.yml          P07: PostgreSQL 18 for the Mac, mounts db/postgres/init.sql
├── db/postgres/init.sql        P07: rooms + reservations tables (portable: SQLite runs the same file)
├── hotel_booking/
│   ├── __init__.py             docstring only - re-exports nothing
│   ├── api.py                  P07: the HTTP edge (Starlette + pydantic): 3 operations + GET /openapi.yaml, problem details
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
│   └── test_capacity.py        P07: capacity.md numbers == capacity.py; peak == l04-notes
├── docs/
│   ├── requirements.md         R1-R6 with Check and Proof lines, invariant
│   ├── design-notes.md         P03, P04, P06 and P07 sections
│   ├── quality-scenarios.md    P05: stakeholders and S1-S6
│   ├── contexts.md             P05: words, four contexts, rule owners, context map, borders (+ P06 status)
│   ├── adr-001-modular-monolith.md   P06: why one program with four modules
│   ├── capacity.md             P07: assumptions, results, checked by hand, what to measure (P08)
│   ├── openapi.yaml            P07: the API contract (OpenAPI 3.1), served at GET /openapi.yaml
│   ├── api-check.md            P07: every request with curl and its exact answer; SQLite run observed
│   ├── requests/               P07: request bodies for curl (maya-r7, omar-r7, omar-r8 + three error bodies)
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

## Known limitations of version 4

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
- Every search asks the database once per room (2 queries today, 133 a second at the estimated
  peak for 40 rooms) — P08 measures it and caches the search.
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
