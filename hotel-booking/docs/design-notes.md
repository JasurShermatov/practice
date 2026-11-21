# P03 design notes

Short answers from each P03 step. Diagrams:
[practices/P03-hotel-domain-uml/Diagrams.md](../../practices/P03-hotel-domain-uml/Diagrams.md).
Later practices add their own sections below the P03 ones.

## Why design before code

Low-level design decides which classes exist (Guest, Room, DateRange, Reservation,
ReservationStore, EmailSender, BookingService), what each one keeps and does, and who calls whom —
for example that BookingService asks ReservationStore `has_overlap(room, stay)` before it saves.
Deciding this first gives every rule exactly one home: the overlap rule lives only in
`DateRange.overlaps()`, so the website and the reception desk can never disagree, and a rule change
(such as a cleaning day after each stay) is one edit, not two.

## Where the methods live

- **`cancel()` lives in `Reservation`**, because cancelling changes the reservation's own status and
  the "already cancelled → return False" rule must be checked in one place. Other code may not set
  the status directly (it is a read-only property); it has to ask the reservation.
- **`has_overlap(room, stay)` lives in `ReservationStore`**, because only the store can see all the
  reservations. It does not repeat the date rule: it asks each row `blocks(room, stay)`, and the
  row asks its `DateRange` `overlaps(...)`.
- `overlaps(other)` lives in `DateRange` (needs only the two pairs of dates); `blocks(room, stay)`
  in `Reservation` (only it knows its status, room and stay); `reserve(...)` in `BookingService`
  (it runs the steps in order: check, save, email, answer).

## Activity traces

Diagram: Activity - book (two decisions, then save → email → Accepted).

1. **Omar, R7, 13–15 Nov** (Maya has R7 12–14): first diamond "Check-out after check-in?" → Yes.
   Second diamond "A Confirmed booking shares a night?" → Yes, the night of the 13th. The request
   ends at **Unavailable · save nothing**.
2. **Nora, R7, 14–16 Nov** (Maya has R7 12–14): first diamond → Yes (16 > 14). Second diamond →
   No (Maya's last night is the 13th; 14 < 14 is false). Save the reservation as Confirmed → send
   the confirmation email → **Accepted R102**.
3. **Omar, R8, 15–15 Nov**: first diamond → No (check-out is not after check-in, zero nights). The
   request ends at **InvalidDates · save nothing**; the second diamond is never reached, so the
   store is not even asked.

## Prediction

Reasoned from the activity trace above (not from the output): Nora asks for R7 14–16 after Maya holds R7 12–14 and Omar was refused.
Prediction: **Accepted R102** — no shared night, and Omar's refused request saved nothing, so the
next id is R102.
Result (**Observed**): `Nora books R7 14-16 Nov: Accepted R102` — matches.

## The race

**Prediction** (reasoned from the check-then-save order of the sequence diagram): when Maya and Omar book R7 for 12–14 Nov at the same moment with a slow step
between check and save, R7 will end with **2 Confirmed reservations**, because both requests can
run `has_overlap` before either runs `save`.

**Result (Observed, `python main.py --race`):** `Maya: Accepted R101`, `Omar: Accepted R102`,
`Confirmed reservations for R7 on 12-14 Nov: 2` — the prediction held.

**What happened:** both requests checked the store while it was still empty, so both got "free",
and each then saved on the strength of its own out-of-date answer — R3 is broken although every
single-request example passes. The problem sits between `self._store.has_overlap(room, stay)` (the
check) and `self._store.save(reservation)` (the act) in `BookingService.reserve`: the two calls are
not one atomic step.

**Not fixed in P03, on purpose.** A lock in the code would only help while the app runs as one
process; real deployments run several copies. P09 fixes it in the database (locks / constraints)
after P07 adds one. The test `test_race_double_books_r7_known_defect` pins the defect so that the
fix will be visible as a deliberate test change.

# P04 design notes

P04 changes the *structure* of the app, not what it does (plus one deliberate new rule, R6, and an
SMS sender, added after the refactoring). Diagrams and evidence:
[practices/P04-refactor-reservation/](../../practices/P04-refactor-reservation/README.md).

## Refactoring

A refactoring changes how the code is organised — names, files, which class depends on which — while
everything the app does for a guest (every answer, every saved booking, every message) stays exactly
the same.

Must stay the same:
- the tests from Step 2 — all 6 still pass after every move;
- the demo output — the same nine lines as in P03;
- the race demo — still "Double booking!": refactoring does not fix bugs (P09 does).

## What our code breaks

- BookingService asks for exactly ReservationStore (D: dependency inversion).
  In P07 we would have to edit BookingService just to use a database.
- BookingService asks for exactly EmailSender (D, and therefore O: open/closed). The day the hotel
  wants SMS confirmations we must open the class that holds the booking rules and change its
  constructor and `reserve()` — a change for a messaging reason in a class whose job is booking.
- There is no seam to make the email fail in a test (D). The only sender is the real EmailSender,
  so nobody can show that a failed message keeps the booking.
- `demo.py` both tells the classroom story and chooses the concrete store and sender (S: two
  reasons to change). P04 moves the choice to `main.py`, the composition root.
- Noted, not fixed: the demo pause (`slow_step_seconds`) sits inside `reserve()`. It is 0 in normal
  use and stays on purpose so the race can still be shown; it goes when the database arrives.

(The course's fourth problem, "all nine classes live in one file", does not apply here: the P03
version of this portfolio was already a package with one module per group of classes.)

## Target design

`BookingService` depends on two promises: `ReservationStore` and `NotificationSender`
(`typing.Protocol`, Python's interfaces). `InMemoryReservationStore` (the P03 list, renamed) and
`EmailNotificationSender` (the P03 email counter, renamed) keep them; `SmsNotificationSender` and the
tests-only `FakeNotificationSender` keep the notification promise too. `main.py` is the only place
that creates the real objects. Picture: "Classes - after" in
[Diagrams.md](../../practices/P04-refactor-reservation/Diagrams.md#2-classes---after-the-activity-sheet-page).

## Proof

- Tests: `python -m unittest -v` → **Ran 6 tests … OK** after every move (6 moves, 6 green runs),
  and the 6 test bodies were not edited (only the imports and `new_service()` changed).
- Demo: `python main.py` → the **same** nine lines as P03 (`diff` against the P03 output: no difference).
- Race: `python main.py --race` → **still double-booked** (`Confirmed reservations for R7 on 12-14 Nov: 2`
  in 20 of 20 runs). Refactoring did not fix the bug; P09 will.

All three are **Observed** (Linux container, Python 3.13.18), recorded in
[evidence/observed-runs.md](../../practices/P04-refactor-reservation/evidence/observed-runs.md).

## Feel the benefit (Step 7)

- **Fake sender:** the tests now pass a `FakeNotificationSender` that remembers ids, so the sixth test
  checks exactly `["R101", "R102"]` instead of a count.
- **R6, test first:** the R6 test failed (`RuntimeError: The mail server is down.` escaped `reserve`),
  then `reserve` gained `_try_to_confirm()`: the booking is saved *before* the message is tried, a
  failure is caught, logged and reported as `notification_failed=True`, and the answer stays
  `Accepted R101`. 7 green.
- **SMS without touching BookingService:** `SmsNotificationSender` is a new class next to the email
  sender; `booking.py` has the same SHA-256 before and after the step. 8 green.

# P06 design notes

P06 turns the four P05 contexts into four modules with checked borders. Like P04 it is a
refactoring: what the app does for a guest must not change. Evidence:
[practices/P06-modular-monolith-review/](../../practices/P06-modular-monolith-review/README.md).

## Before

- Tests: `python -m unittest -v` → **Ran 8 tests … OK** (full suite `python -m pytest`: 82 passed).
- Demo: `python main.py` → the nine lines, ending `Confirmation emails sent: 2`.
- Race: `python main.py --race` → `Confirmed reservations for R7 on 12-14 Nov: 2` — **Double booking!**

## Modules

| Module | Public contract (others may use) | Internal code (only the module, the wiring and the tests) |
| --- | --- | --- |
| Rooms | `Room`, `RoomCatalog` (the room catalog promise) | `InMemoryRoomCatalog` |
| Reservations | `BookingService`, `BookingResult` (+ `BookingOutcome`), `Reservation`, `DateRange`, `Guest`, `ReservationStatus`, `ReservationStore` (the store promise) | `InMemoryReservationStore` |
| Payments | `PaymentStatus`, `PaymentService` (the payment service promise) | `SimulatedPaymentService` |
| Notifications | `Confirmation`, `NotificationSender` (the notification sender promise) | `EmailNotificationSender`, `SmsNotificationSender` |

In Python a module is a package: `hotel_booking/<module>/__init__.py` is the contract,
`internal.py` the internal code. `hotel_booking/__init__.py` no longer re-exports anything.

## Architecture rules

1. **Reservations uses only the public contracts of other modules.** BookingService may use the
   Notifications contract (`NotificationSender`, `Confirmation`), never the email sender.
2. **Rooms does not depend on any other module.** Rooms knows nothing about reservations, money or
   messages; it is the base the others build on.
3. **Payments and Notifications do not depend on Reservations.** Every arrow points away from
   Reservations, so there is no dependency circle.

Written once in `../.importlinter`; checked by `lint-imports` and, without installing anything, by
`tests/test_architecture.py` (stdlib `ast`, reads the same file). Two extra checks there: no module
imports another module's internal code, and every class lives in one of the four modules.

## Broken on purpose

Rule 1 failed: adding `from hotel_booking.notifications.internal import EmailNotificationSender` to
`reservations/booking.py` gave "Reservations uses only the public contracts of other modules
BROKEN — `hotel_booking.reservations.booking -> hotel_booking.notifications.internal (l.29)`",
while the 8 booking tests stayed green; removing the line made all checks green again.

## After

- Tests: `python -m unittest -v` → **Ran 8 tests … OK**, same 8 test methods (only imports, the fake
  sender and the R6 logger name adapted); plus **3 contracts kept** (`python -m tests.test_architecture`;
  `lint-imports` on a machine with import-linter). Full suite: see the practice README.
- Demo: the **same nine lines** as in "Before" (`diff`: no difference).
- Race: **still double-booked** (`Confirmed reservations for R7 on 12-14 Nov: 2`). Moving code into
  modules does not fix the race; P09 does — and only inside Reservations.

Same as "Before": yes, all three.

## Decisions made while moving

- `Confirmation` is built inside `BookingService._try_to_confirm`, on Reservations' side of the
  border, after `save` — Notifications never sees a `Reservation`, so a sender can no longer
  cancel or change a booking (the P04 "cancelling sender" counter-example is now impossible).
- The wiring asks `InMemoryRoomCatalog.all()` for the rooms; `BookingService` keeps its P04
  constructor (a room list), so the 8 tests did not change.
- `demo.py` stays in the package as the classroom scenario but now names only contracts:
  `run_demo` receives `lambda: email.sent` instead of the internal sender.
- Payments' amount is `Decimal`, not `float` (P05 recommendation). Payments is not wired yet —
  nothing calls it before the P17 saga. P05 decision D1 (`deposit_for`) is deferred to P17.

# P07 design notes

The P06 app gets an address and a database: an HTTP API on http://localhost:5080
(`hotel_booking/api.py`, Starlette + pydantic, served by uvicorn) and its reservations in a
database through the same `ReservationStore` promise (`SqlReservationStore`: SQLite by default,
PostgreSQL from `docker-compose.yml` on the Mac). `BookingService` and the booking rule did not
change. Estimate: [capacity.md](capacity.md); contract: [openapi.yaml](openapi.yaml); proof:
[api-check.md](api-check.md).

## API decisions

- **Free rooms come in text order of the room number** — R10 before R7, because room numbers are
  text and text is compared character by character. `after` is compared the same way, so a client
  that pages with `after=<next>` never skips or repeats a room, whatever the numbers look like.
- **Clients compare `title`, never `detail`.** `title` is one of a fixed list (the five operation
  titles plus MethodNotAllowed and InternalError); `detail` is a sentence for people and may be
  reworded without breaking anybody.
- **The room type is catalog data, not a fixed list.** It comes from the `rooms` table (Standard,
  Deluxe, …); a new type is a new row, not a new API version.
- Further decisions (mine): every error — also an unknown path, a wrong method and a server
  failure — has the same problem-details shape; the endpoint checks only what BookingService
  cannot know (request shape, real dates, known room) and calls it exactly once; DELETE is
  idempotent, POST is not (a retried booking gets 409 for its own stay — Idempotency-Key in P11);
  answers may gain fields but never lose or rename one; 201 has no `Location` header because there
  is no `GET /reservations/{id}` to point at yet.

## API tests

The course's four, in `test_api.py` (list store, Starlette TestClient):

| Test | Request | Expected answer |
|---|---|---|
| Search | `GET /rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14` | 200, exact body with R7 and R8, `"next":null` |
| Book, then book again | `POST` Maya R7 12–14; `POST` Omar R7 13–15 | 201 `{"id":"R101","status":"Confirmed","notificationFailed":false}`, then 409 Unavailable |
| Wrong dates | `POST` with checkOut = checkIn | 400 InvalidDates as `application/problem+json`, exact body |
| Cancel twice | `POST` Maya, `DELETE /reservations/R101` twice | 204, then 404 NotFound |

Changing 409 to 201 in the second test made it fail (`AssertionError: 201 != 409`); changed back:
green. Every other error path is in `tests/test_api_http.py`; the contract is checked against the
code in both directions by `tests/test_openapi_contract.py`.

## After

- Checks: `python -m unittest` → **Ran 12 tests … OK** (8 behaviour + 4 API); border contracts
  **5 kept** (the course's 3 + 2 for the API edge); full suite and document checks green — numbers in
  the P07 README.
- The seven answers of `api-check.md`: **all exactly as expected**, on SQLite, against the real app
  started with `python main.py` (uvicorn) and called with `curl` — plus 14 more requests for every
  other error path, paging, 404/405 and the contract.
- Restart check: Maya's R102 **survived** stopping and starting the app; the table holds R101
  Cancelled and R102 Confirmed. On PostgreSQL: the same SQL ran on a PostgreSQL 16 server through
  `psql`; the full Docker + psycopg run is the student's Mac check.

## Decisions made while building

- **Autoflush in the SQL store.** The first version wrote status changes only in `save_changes`,
  so inside one unit of work a cancel did not free the room for the next question — the list store
  and the SQL store answered differently (found by the shared store test). The store now writes
  pending changes before an overlap question; commit is still once, at the end of the request.
- **One schema file for both databases.** `db/postgres/init.sql` is portable; the SQLite wiring
  runs the same file, so the tables cannot drift apart. It adds a partial index for the overlap
  question (133 of them a second at the estimated peak).
- **The race is still there.** Through HTTP and SQLite, two simultaneous bookings of R7 either
  both succeed (R101 and R102: double booking) or — when both number theirs R101 — the second is
  refused by the primary key with a 500. Both outcomes are pinned by tests until P09.

# P08 design notes

Session: Saturday 7 November 2026 (P08 — cache and scale experiment). Start state: the P07
project with every check green (12 unittest tests, 5 border contracts, 335 pytest tests, 95
document checks — [b0-baseline](../../practices/P08-cache-scale-experiment/evidence/logs/b0-baseline.txt)).
`capacity.md` "To measure later" had two open P08 lines; both are answered in
[cache-experiment.md](cache-experiment.md).

## Measure first

`GET /stats` (counters: searches, databaseQueries, cacheHits, cacheMisses, cacheErrors) and a
`CountingReservationStore` that the wiring puts around the SQL store; `tools/measure.py` sends
1,000 searches and prints average, p95, total and the counter difference. Without a cache:
**2,000 queries for 1,000 searches** — one per room per search, exactly as P07 estimated.

## Cache rule

Booking never reads the cache.

- Only `GET /rooms/availability` reads it (cache-aside); `POST` and `DELETE` decide from the
  database and only *raise the version* after their unit of work has committed.
- Key `availability:v{version}:{checkIn}:{checkOut}`, value `R7,R8`, TTL 30 s; the key is built
  before the database is asked.
- The cache lives at the HTTP edge (`api_cache.py`, `api_redis.py`) and knows no module; the
  borders say so (`.importlinter`, 6 contracts) and an `ast` test proves that `reserve` and
  `cancel` never call the cache's lookup.

## Invalidation

A successful `POST` (201) or `DELETE` (204) runs `INCR availability:version` after the unit of
work; 400, 404 and 409 change nothing and leave the version alone. The course's two cache tests
are in `test_api.py`; removing the invalidate line makes the second one fail (seen:
[break-the-cache](../../practices/P08-cache-scale-experiment/evidence/logs/break-the-cache.txt)).

## After

- Checks: `python -m unittest` → **Ran 14 tests … OK** (8 behaviour + 6 API); border contracts
  **6 kept**; the full pytest suite and every document check green — numbers in the P08 README.
- Measurements (median of 5 runs, 1,000 searches): no cache **2,000 queries, avg 0.92 ms, p95
  1.31 ms**; Redis cache **2 queries, 999 hits, avg 0.72 ms, p95 1.13 ms**; with 40 rooms
  40,000 → 40 queries and p95 1.86 → 1.22 ms.
- Stale result: without invalidation the third search still listed R7 after Maya booked it, and
  Omar got 409 (booking reads the database); with invalidation the third search showed R8 only.

## Decisions made while building

- **No redis-py.** It could not be installed in the build environment, so `api_redis.py` speaks
  Redis's protocol (RESP2) with the standard library: five commands, a connection pool, a 0.5 s
  timeout. It keeps the same `KeyValueStore` promise; swapping in redis-py would change one file.
- **Edge files, not new modules.** Stats, the counting store and the cache measure or speed up the
  HTTP edge; they hold no hotel rule. They sit next to `api.py`, and `api.py` itself still defines
  only pydantic shapes (architecture test).
- **Fail-open cache** (differs from the course reference): when Redis does not answer, searches go
  to the database and bookings are still answered 201; `cacheErrors` and the log show the outage.
  The app still refuses to *start* without Redis, so a wrong address is noticed at once.
- **`X-Cache` header** (`hit`, `miss`, `bypass`) on every search answer, documented in the contract:
  it made the stale result visible with plain `curl`.
- **A fifth counter** (`cacheErrors`) next to the course's four; the course's `/stats` text in the
  cache test therefore ends with `"cacheErrors":0`.
- **`--cache off|memory|redis` and `--no-invalidation`** in `main.py`: the "No cache" row and the
  Step 5 stale result can be reproduced with the final code instead of editing it back and forth.
