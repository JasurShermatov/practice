# P09 Worksheet — answers to every "Your turn"

Student: Jasur Shermatov · Group 23-309 SW · Session: Tuesday 10 November 2026, 18:00–19:20, room 222.
Evidence labels as agreed in L01: **Observed** (run, output in [evidence/logs](evidence/logs/)),
**Simulated**, **Proposed**. Where the course uses Docker, PostgreSQL 18 and two terminals, this
build used a local PostgreSQL 16, real uvicorn processes and scripted psql sessions. The
substitutions are listed in the [README](README.md#substitutions-honest-record).

## §1 · Open your project

1. *Docker Desktop.* **To do by the student** on the Mac. There is no Docker daemon in the build
   container, so a local PostgreSQL 16 cluster and a local redis-server stood in (E1).
2. *Open the folder and three terminals.* Done. The two app instances, psql and the race tool are
   run by [race_experiment.py](evidence/race_experiment.py) and [postgres_repairs.py](evidence/postgres_repairs.py).
3. *P08 checks green.* **Observed** ([b0-baseline](evidence/logs/b0-baseline.txt)): `python -m unittest`
   ran 14 tests OK, there are 6 border contracts kept, and the full suite shows 427 passed. The race
   still double-books (`--race` printed "Double booking!").
4. *Read `docs/l05-notes.md`.* Written as [l05-notes.md](../../hotel-booking/docs/l05-notes.md):
   three answers, which are the invariant and write skew, the constraint in the database, and the
   limits and evidence. The repair I chose there is the one built in Step 7.
5. *`# P09 design notes`.* Added to [design-notes.md](../../hotel-booking/docs/design-notes.md#p09-design-notes).

## §2 · Step 1 — Reproduce the double booking

1. *The sequence (1.1).* `CREATE SEQUENCE reservation_ids START 101;` is in
   [db/postgres/init.sql](../../hotel-booking/db/postgres/init.sql). For a running database the
   `setval(...)` statement is in [p09-upgrade.sql](../../hotel-booking/db/postgres/p09-upgrade.sql).
   Both were run on PostgreSQL 16 (E5, E11). SQLite has no sequences, so it uses the one-row table
   `reservation_ids` in [db/sqlite/init.sql](../../hotel-booking/db/sqlite/init.sql).
2. *`next_reservation_id` in the contract and both stores (1.2).* It is in `ReservationStore`
   ([booking.py](../../hotel-booking/hotel_booking/reservations/booking.py)). `InMemoryReservationStore`
   uses a counter under its lock. `SqlReservationStore` uses `nextval('reservation_ids')` on
   PostgreSQL and `UPDATE reservation_ids … RETURNING` on SQLite. `reserve` calls it, and
   `BookingService._next_id` (the count) is gone. Tests:
   `test_ids_come_from_the_store_and_are_never_handed_out_twice`, `test_fifty_threads_get_fifty_different_ids`,
   `test_eight_connections_on_sqlite_one_reservation_and_eight_different_ids`,
   `test_postgres_ids_come_from_the_sequence`.
3. *HOTEL_SLOW_STEP and HOTEL_PORT (1.3).* Both are in [main.py](../../hotel-booking/main.py),
   alongside `--slow-step` and `--port`, and both reach the server
   (`test_slow_step_and_port_come_from_the_environment`).
4. *Checks still green, nothing repaired yet.* The course does Step 1 before the repair. In this
   portfolio the code change was made in one piece, so the pre-repair state was run from a copy of
   version 5 (the P08 end state) instead. The same race tool ran against that copy (item 6).
5. *The race tool (1.4).* [tools/race_http.py](../../hotel-booking/tools/race_http.py) is my own
   stdlib version of the course tool. It has the same output and adds `--repeat`, `--stagger`,
   `--json` and exit codes 0, 1 and 2.
6. *Run it with HOTEL_SLOW_STEP=1.* **Observed** against version 5 on SQLite and against the
   no-constraint PostgreSQL database:
   `Maya -> 201 Created … R101`, `Omar -> 201 Created … R102`, "DOUBLE BOOKED"
   ([race-http-before-after](evidence/logs/race-http-before-after.txt)).
7. *Count in psql.* There were two Confirmed rows for R7, R101 and R102. The tables were read from
   SQLite and from PostgreSQL directly, not through the app (same log).

## §3 · Step 2 — Write the interleaving down

1–2. [docs/interleaving.md](../../hotel-booking/docs/interleaving.md) contains my own race output
under "What I ran".
3. *The eight-row table.* It uses my own run, with the server's timestamps from PostgreSQL 16
   (`race-no-rule` in [postgres-repairs](evidence/logs/postgres-repairs.txt)): Maya BEGIN/check 0.00 s,
   Omar BEGIN/check ≈0.5 s, Maya INSERT 1.00 s, Omar INSERT ≈1.5 s, Maya COMMIT ≈2.0 s, Omar COMMIT ≈2.5 s.
4. *Anomaly.* It is write skew: both read the same empty set and each inserted a different row.
   Repeatable Read does not stop it because no row that either of them read was changed. This was
   observed: two rows at REPEATABLE READ, and the second COMMIT aborted with 40001 at SERIALIZABLE.
5. *Why `SELECT … FOR UPDATE` on the reservations does not help.* At check time no overlapping
   reservation exists yet, so there is nothing to lock. Observed: "locked 0 rows" in both sessions,
   and two Confirmed rows.
6. *The four-repairs table.* It is filled in with the measurements below.

## §4 · Step 3 — A lock inside the app

1. *Read `save`.* `InMemoryReservationStore.save` checks (`_blocked`) and appends under
   `self._lock`. It also refuses a duplicate id, which is the primary key's job.
2–3. *`python main.py --race`.* **Observed**: "Maya: Accepted R101 / Omar: Unavailable / … 1 / Only
   one guest has R7." ([f-race](evidence/logs/f-race.txt)).
4. *First row of the table.* Added as "In-process lock". The web app with one process-wide lock
   around each request was also measured, in item 5 of §5.

## §5 · Step 4 — A second instance

1–2. Two uvicorn processes were started on two ports against one SQLite file (and against one
     PostgreSQL database), with one Redis. Both answered `GET /stats`, which the experiment waits for.
3–4. *The race to two instances, then count.* **Observed** for version 5 on two instances: double
     booking in every round. With the in-process lock on two instances: also double-booked in every
     round. With one instance the lock gave one 201 and one 409 in every round. The counts are in
     the [README](README.md#race-results).
5. *"With one instance, yes. With two, no."* is written in the table.
6. *Where must the rule live?* In the thing every process shares and every writer must pass
   through, which is the database. A rule held by two separate locks is not held at all.

## §6 · Step 5 — SELECT … FOR UPDATE on a guard row

1. `room_booking_guard` (R7, R8, version 0) was created in the experiment database.
2–5. Terminal A (Maya) holds the guard row for 1 s. Terminal B (Omar) starts 0.1 s later and stops
     at its `FOR UPDATE`. It continues the instant A commits. Its check then says 1, not 0, and it
     inserts nothing.
6. Omar's check says 1 and he commits without inserting (timeline in [postgres-repairs](evidence/logs/postgres-repairs.txt)).
7. *Row in the table.* **Observed** waits are in [interleaving.md](../../hotel-booking/docs/interleaving.md#the-four-repairs-and-what-each-one-cost).

## §7 · Step 6 — Optimistic version checking

1. Each run starts on a fresh database with the guard row at version 0.
2–4. Neither terminal waits. Omar's `UPDATE … WHERE version = 0` matched **1** row. Maya's later
     one matched **0** rows. That is not an error, just a fact.
5. Maya rolled back, read the version again (1) and checked again (1), and was refused.
6. *Row in the table.* Nobody waited. The loser redid about 1 s of work (measured). The retry repeats
   the overlap check as well, and in real code it needs a limit.

## §8 · Step 7 — Teach the database the rule

1. *ALTER TABLE first, read the error, cancel, run again.* **Observed** with the upgrade file on a
   version-5 database holding R101 and R102: `ERROR: could not create exclusion constraint
   "reservations_no_overlap"`. The upgrade is one transaction, so not even the sequence was left
   behind. `db/find-double-bookings.sql` named the pair. After
   `UPDATE … SET status = 'Cancelled' WHERE id = 'R102'` the file printed `ALTER TABLE`, and
   `nextval` continued at 103.
2. *btree_gist + the constraint in init.sql (7.4).* Both are in [db/postgres/init.sql](../../hotel-booking/db/postgres/init.sql).
   Without btree_gist PostgreSQL said `data type text has no default operator class for access method "gist"` (observed).
3. *Drop the guard table.* It never entered the project schema. It existed only in the throw-away
   experiment databases, which are dropped after each scenario.
4. *Map the violation (7.5) and answer Unavailable (7.6).* `is_overlap_refusal` checks SQLSTATE 23P01
   plus the constraint name (PostgreSQL), or SQLITE_CONSTRAINT_TRIGGER plus the name (SQLite). On
   PostgreSQL the INSERT runs in a savepoint. `reserve` catches `OverlapRejected` and answers
   Unavailable, and the API answers 409 with the same body.
5. *The two tests (7.7).* They are in [test_api.py](../../hotel-booking/test_api.py). Checks:
   **16 tests OK**, 6 contracts kept (the course's count is "19 green: 16 tests + 3 contracts").
6. *Direct INSERT in psql.* Refused: `ERROR: 23P01: conflicting key value violates exclusion
   constraint "reservations_no_overlap"`. On SQLite it is refused by the trigger
   (`test_the_database_refuses_a_double_booking_typed_straight_in`).
7. *Race against two instances again.* One 201, one 409 and one Confirmed row, in every round, on
   SQLite and on PostgreSQL (README, Race results).
8. *Constraint row.* Added, including the clean-up it needed.

## §9 · Step 8 — ADR-003

1–4. [docs/adr-003-booking-concurrency.md](../../hotel-booking/docs/adr-003-booking-concurrency.md)
     has the five headings. All three rejected repairs, plus Serializable, are there with their
     measured costs. Consequences include that the constraint could not be added until R102 was
     cancelled. There are three revisit conditions.
5. *Compared with the completed example.* Mine is longer where I had numbers: the waits, the
   SQLite trigger limit, and the id race.

## §10 · Check your project and hand it over

1. *Every check.* It is ticked in the [README checklist](README.md#check-your-project-activity-sheet-10).
2. *Commit "P09: protect the booking rule in the database".* **To do by the student.** Git is not
   used in this build.
3. *Re-read the ADR as a stranger.* Done. Every rejected repair has a reason and a number.
4. *Bring the folder to P10.* **To do by the student.**
