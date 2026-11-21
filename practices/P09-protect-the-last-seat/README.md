# P09 — Protect the last seat

**Session:** Tuesday 10 November 2026, 18:00–19:20 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 222
**Related lecture:** L05 — Application concurrency and database correctness (transaction boundaries,
constraints, isolation, optimistic/pessimistic concurrency)
**Type of work:** evolution of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 5 → version 6). This practice reproduces the race, traces it, measures four repairs, keeps
the one that cannot be forgotten, and records the decision as ADR-003.

## Goal

Since P03 two guests who book R7 for the same nights at the same moment have both been told "yes".
P09 makes that happen on purpose (and measurably), writes the interleaving down, compares the
in-process lock, `SELECT … FOR UPDATE` on a guard row, optimistic version checking and the exclusion
constraint with real numbers, and repairs the app so that **exactly one booking wins and the other
gets 409 Unavailable**. The repair holds for one or two instances, on SQLite and on PostgreSQL, and
also for a statement typed straight into psql. The pinned known-defect tests become regression
tests.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| §1 Open your project | P08 checks green first; L05 answers; `# P09 design notes` | [b0-baseline](evidence/logs/b0-baseline.txt), [l05-notes.md](../../hotel-booking/docs/l05-notes.md), [design-notes § P09](../../hotel-booking/docs/design-notes.md#p09-design-notes) |
| 1 · Reproduce it | Id sequence; `next_reservation_id` in the contract and all stores; `HOTEL_SLOW_STEP`, `HOTEL_PORT`; the race tool; the race run for real and the rows counted in the database | [db/postgres/init.sql](../../hotel-booking/db/postgres/init.sql), [booking.py](../../hotel-booking/hotel_booking/reservations/booking.py), [internal.py](../../hotel-booking/hotel_booking/reservations/internal.py), [main.py](../../hotel-booking/main.py), [tools/race_http.py](../../hotel-booking/tools/race_http.py), [race-http-before-after](evidence/logs/race-http-before-after.txt), [id-allocation](diagrams/id-allocation.svg) |
| 2 · Write it down | `docs/interleaving.md`: own race output, eight-row trace (server timestamps), anomaly, why FOR UPDATE on reservations cannot help, four-repairs table | [interleaving.md](../../hotel-booking/docs/interleaving.md), [race-double-booking](diagrams/race-double-booking.svg), [postgres-repairs](evidence/logs/postgres-repairs.txt) |
| 3 · A lock inside the app | The list store checks and appends under its lock; `--race` → "Only one guest has R7." | [internal.py](../../hotel-booking/hotel_booking/reservations/internal.py) `InMemoryReservationStore`, [f-race](evidence/logs/f-race.txt) |
| 4 · A second instance | Two uvicorn processes, one database; the lock (applied to the web app) fails across processes | [race_experiment.py](evidence/race_experiment.py), [serve.py](evidence/serve.py) `--app-lock`, [in-process-lock-two-instances](diagrams/in-process-lock-two-instances.svg) |
| 5 · FOR UPDATE on a guard row | Guard table; terminal B waits; wait measured (5 runs) | [postgres_repairs.py](evidence/postgres_repairs.py) `guard-row`, [guard-row-for-update](diagrams/guard-row-for-update.svg) |
| 6 · Optimistic version | Version check: nobody waits, the loser's UPDATE matches 0 rows, retries and refuses (5 runs) | `optimistic-version` in the same log, [optimistic-version](diagrams/optimistic-version.svg) |
| 7 · The exclusion constraint | btree_gist + named constraint in init.sql; refused over dirty data, then accepted; store maps 23P01 → `OverlapRejected`; service → Unavailable; API → 409; the course's two tests; direct INSERT refused; race repaired across two instances | [init.sql](../../hotel-booking/db/postgres/init.sql), [p09-upgrade.sql](../../hotel-booking/db/postgres/p09-upgrade.sql), [find-double-bookings.sql](../../hotel-booking/db/find-double-bookings.sql), [internal.py](../../hotel-booking/hotel_booking/reservations/internal.py), [test_api.py](../../hotel-booking/test_api.py), [race-fixed-exclusion-constraint](diagrams/race-fixed-exclusion-constraint.svg) |
| 7 (SQLite) | The same rule for the default/test database: triggers + id table, upgrade of version-5 files | [db/sqlite/init.sql](../../hotel-booking/db/sqlite/init.sql), [db/sqlite/p09-upgrade.sql](../../hotel-booking/db/sqlite/p09-upgrade.sql), [race-fixed-sqlite-trigger](diagrams/race-fixed-sqlite-trigger.svg) |
| 8 · ADR-003 | Context, decision, three rejected repairs (+ Serializable) with measured costs, consequences incl. the clean-up, when to revisit | [adr-003-booking-concurrency.md](../../hotel-booking/docs/adr-003-booking-concurrency.md) |
| §10 Check and hand over | Every check of the sheet's table, run once more | [Check your project](#check-your-project-activity-sheet-10), [f-* logs](evidence/logs/) |
| Brief: conflicts → correct HTTP status, in the API and OpenAPI | 409 Unavailable for the race loser (same body), no more 500 for a duplicate id; contract 1.2.0 with the `lostTheRace` example produced by a real race | [openapi.yaml](../../hotel-booking/docs/openapi.yaml), [test_openapi_contract.py](../../hotel-booking/tests/test_openapi_contract.py) |
| Brief: known-defect tests → regression tests | Each deliberate change documented | [Deliberate test changes](#deliberate-test-changes) |
| Brief: why an in-process lock is not enough across processes | Explained and measured (two instances: every round double-booked) | [interleaving.md § four repairs](../../hotel-booking/docs/interleaving.md#the-four-repairs-and-what-each-one-cost), [Race results](#race-results) |
| Brief: PostgreSQL mechanism shown on a real PostgreSQL 16 | Concurrent psql sessions for each repair and the isolation levels; the app's own SQL store against PostgreSQL through two instances | [postgres-repairs](evidence/logs/postgres-repairs.txt), [race-http-before-after](evidence/logs/race-http-before-after.txt), [What was and was not observed](#what-was-and-was-not-observed) |
| Diagrams (Mermaid, render-checked) | Race, fix (PostgreSQL, SQLite), lock across instances, guard row, version, ids, four repairs, class diagram (used by the UML conformance test) | [diagrams/](diagrams/), [mmdc log](evidence/logs/mmdc.txt) |
| Evidence, worksheet, reflection | | [evidence/Index.md](evidence/Index.md), [observed-runs.md](evidence/observed-runs.md), [Worksheet.md](Worksheet.md), [reflection](reflections/Jasur-Shermatov.md) |
| Document checks | Sections, numbers = logs, diagrams = code, links, README row | [checks/test_p09_docs.py](checks/test_p09_docs.py) |

## Race results

**Observed** — [race-http-before-after](evidence/logs/race-http-before-after.txt) (all ten configurations,
[json](evidence/logs/race-results.json)) and [race-http-postgres-after-the-retry](evidence/logs/race-http-postgres-after-the-retry.txt)
([json](evidence/logs/race-results-postgres-after-the-retry.json)). Linux container, Python 3.13.18,
SQLite 3.53.1, PostgreSQL 16.15, redis-server 7.0.15. Every instance is a separate uvicorn process;
"2 instances" means Maya → one process, Omar → the other, one shared database. After each round the
tool cancels what it booked, so every round starts with R7 free. "Refused by the database" = ids the
database handed out minus rows written: a booking that passed the pre-check and was then refused by
the trigger or the constraint, so it **lost the race and was saved by the database**. "Other" answers
were 500: duplicate id R101 in version 5 (`UNIQUE constraint failed: reservations.id`), and
`deadlock detected` (40P01) in the first PostgreSQL run, which led to the retry in the store.

| Key | What ran | Confirmed rows after the single course run | 20 rounds, slow step 1 s, Omar +0.5 s: double-booked | … one 201 + one 409 | … loser refused *by the database* | Simultaneous pairs, no slow step: double-booked / other answers (500) | … loser refused by the database |
|---|---|---|---|---|---|---|---|
| `v5-sqlite-1` | version 5 (P08), SQLite, 1 instance | 2 | 20 of 20 | 0 | - | 4 / 63 (of 100) | - |
| `v5-sqlite-2` | version 5, SQLite, 2 instances | 2 | 20 of 20 | 0 | - | 11 / 26 (of 100) | - |
| `v5-lock-1` | version 5 + in-process lock, 1 instance | 1 | 0 of 20 | 20 | - | 0 / 0 (of 100) | - |
| `v5-lock-2` | version 5 + in-process lock, 2 instances | 2 | 20 of 20 | 0 | - | 5 / 27 (of 100) | - |
| `v6-sqlite-1` | version 6, SQLite (triggers), 1 instance - `python main.py` | 1 | 0 of 20 | 20 | 21 | 0 / 0 (of 100) | 71 |
| `v6-sqlite-2` | version 6, SQLite (triggers), 2 instances - `python main.py` | 1 | 0 of 20 | 20 | 21 | 0 / 0 (of 100) | 41 |
| `v6-pg-norule-1` | version 6 code, PostgreSQL 16 **without** the constraint, 1 instance | 2 | 20 of 20 | 0 | 0 | 84 / 0 (of 100) | 0 |
| `v6-pg-norule-2` | version 6 code, PostgreSQL 16 **without** the constraint, 2 instances | 2 | 20 of 20 | 0 | 0 | 90 / 0 (of 100) | 0 |
| `v6-pg-1` | version 6, PostgreSQL 16 + exclusion constraint, 1 instance (first run) | 1 | 0 of 20 | 20 | 21 | 0 / 1 (of 100) | 93 |
| `v6-pg-2` | version 6, PostgreSQL 16 + exclusion constraint, 2 instances (first run) | 1 | 0 of 20 | 20 | 21 | 0 / 6 (of 100) | 95 |
| `v6-pg-1` (rerun after the retry fix) | version 6, PostgreSQL 16 + exclusion constraint, 1 instance **after the 40P01 retry**, 300 pairs | 1 | 0 of 20 | 20 | 21 | 0 / 0 (of 300) | 275; PostgreSQL logged 15 x 40P01 |
| `v6-pg-2` (rerun after the retry fix) | version 6, PostgreSQL 16 + exclusion constraint, 2 instances **after the 40P01 retry**, 300 pairs | 1 | 0 of 20 | 20 | 21 | 0 / 0 (of 300) | 268; PostgreSQL logged 7 x 40P01 |

In short: **before** the fix every configuration double-booked 20 of 20 slow-step rounds. The
in-process lock fixed one instance and failed again with two (20 of 20). **After** the fix: 0 of 20
everywhere. With both requests sent at once, the database refused the loser in 41–95 % of the pairs,
which is the race that the pre-check alone misses (version 5 double-booked or failed in 37–67 of 100
pairs). The first PostgreSQL run returned 1 and 6 deadlock 500s. The store now retries those, and in
the rerun 300 of 300 pairs ended with one 201 and one 409.

## How to check

```bash
cd hotel-booking
python3 -m unittest -v                 # Ran 16 tests ... OK   (8 booking + 8 API, the course's "16 tests")
python3 -m tests.test_architecture     # Contracts: 6 kept, 0 broken.
python3 -m pytest                      # 479 passed (incl. tests/test_concurrency.py)
python3 -m mypy                        # Success: no issues found
python3 main.py --race                 # ... Omar: Unavailable ... Only one guest has R7.
HOTEL_SLOW_STEP=1 python3 main.py      # terminal 1 (Redis running, or add --cache memory)
HOTEL_SLOW_STEP=1 HOTEL_PORT=5081 python3 main.py   # terminal 2
python3 tools/race_http.py http://localhost:5081    # terminal 3: one 201, one 409
cd ..
python3 -I practices/P09-protect-the-last-seat/evidence/race_experiment.py hotel-booking <copy of version 5>   # all race configurations
python3 -I practices/P09-protect-the-last-seat/evidence/postgres_repairs.py hotel-booking                    # Steps 1-7 in psql, timed (needs PostgreSQL 16 binaries)
python3 -m pytest -p no:cacheprovider practices/*/checks                                                     # P05-P09 document checks
bash practices/P09-protect-the-last-seat/evidence/render_diagrams.sh                                         # re-render + mmdc log
```

On the Mac, with Docker: `docker compose up -d` (a new volume gets the new `init.sql`). For the
existing P08 volume run `docker compose exec -T db psql -U hotel -d hotel -v ON_ERROR_STOP=1 < db/postgres/p09-upgrade.sql`
(cancel any pair that `db/find-double-bookings.sql` lists first), then `pip install "psycopg[binary]"`
and `python main.py --db postgres`.

## What changed in the code (version 5 → 6)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/reservations/booking.py` | `OverlapRejected`; `ReservationStore.next_reservation_id`; `save` promises to refuse an overlap; `reserve` takes the id from the store and answers `OverlapRejected` with Unavailable; `_next_id` (count) removed | module contract + rule |
| `hotel_booking/reservations/__init__.py` | exports `OverlapRejected` | module contract |
| `hotel_booking/reservations/internal.py` | List store: lock, counter, check in `save`, duplicate-id refusal. SQL store: `next_reservation_id` (`nextval` / SQLite `UPDATE … RETURNING`), savepoint around the INSERT on PostgreSQL, `is_overlap_refusal` (23P01 + name / SQLite trigger + name) | internal |
| `hotel_booking/api_stats.py` | Counting store passes `next_reservation_id` on (counted as a database question) | edge |
| `hotel_booking/api.py`, `rooms/`, `payments/`, `notifications/` | **unchanged**: 409 already meant Unavailable | — |
| `db/postgres/init.sql` | + btree_gist, `CONSTRAINT reservations_no_overlap EXCLUDE USING gist`, `CREATE SEQUENCE reservation_ids` | schema |
| `db/sqlite/init.sql` (new), `db/sqlite/p09-upgrade.sql` (new), `db/postgres/p09-upgrade.sql` (new), `db/find-double-bookings.sql` (new) | SQLite translation; upgrades of version-5 databases (refused over double bookings) | schema |
| `main.py` | SQLite runs `db/sqlite/init.sql` or upgrades a version-5 file (`UpgradeRefused`); `HOTEL_SLOW_STEP`/`--slow-step`, `HOTEL_PORT`; `ServerOptions.slow_step_seconds`; version 6 | wiring |
| `hotel_booking/demo.py` | docstrings only (`run_race` is unchanged; its output changes because the store changed) | docs |
| `tools/race_http.py` (new) | The race tool (course output + `--repeat`, `--stagger`, `--json`, exit codes) | tool |
| `docs/openapi.yaml` | 1.2.0: the simultaneous-bookings promise, 409 description + `lostTheRace` example, 500 description | contract |
| `docs/` | `interleaving.md`, `adr-003-booking-concurrency.md`, `l05-notes.md` (new); design-notes § P09; capacity.md (id statement wording); quality-scenarios S2 and requirements R3 status | docs |
| `pyproject.toml`, `requirements.txt`, `README.md`, `capacity.py` (comment) | version 0.9.0; mypy files; no new package; README version 6 | config/docs |

## Deliberate test changes

Old tests after the code change, before any test was touched: **18 failed / 409 passed**
([b1](evidence/logs/b1-old-tests-after-the-code-change.txt)). Each failure is an expected
consequence of the fix and was changed on purpose. The reason is written in each module's
docstring:

| Test (version 5) | Now | Why |
|---|---|---|
| `test_demo_and_race.py::test_race_double_books_r7_known_defect` | `test_race_gives_r7_to_exactly_one_guest_regression` | It pinned the defect. Same race and timing, now "Omar: Unavailable", 1 Confirmed |
| `test_demo_and_race.py::test_main_race_flag_still_double_books` | `test_main_race_flag_gives_r7_to_one_guest` | Same reason. The sheet's Step 3 output, line by line |
| `test_api_sqlite.py::test_race_through_the_database_still_double_books_known_defect` | `test_race_through_the_database_gives_the_room_to_one_guest` | It pinned the defect. Now 201 R101 + 409, one Confirmed row, the id counter at 102 |
| `test_api_sqlite.py::test_two_requests_numbering_r101_the_primary_key_refuses_the_second` | `test_a_booking_made_while_another_is_uncommitted_gets_its_own_id_and_a_409` | It pinned the duplicate-id 500. Now Omar gets R102 from the database, and the trigger refuses him: 409 |
| `test_sequences.py` (3 tests) | same names | `store.count() -> 0` became `store.next_reservation_id() -> R101` at the same position. In the race log the second save is now refused and no confirmation is sent |
| `test_sql_store.py::test_save_changes_writes_only_the_statuses_that_changed` | same | SQLite's trace hook prints the UPDATE twice once a trigger exists, so the test counts changed rows instead |
| `test_sql_store.py::test_sqlite_runs_the_file_docker_compose_mounts_into_postgresql` | `test_sqlite_and_postgresql_schemas_declare_the_same_tables` + 2 checks | SQLite cannot run the PostgreSQL file any more. The drift check keeps the two files equal where they must be |
| `test_sql_store.py::test_schema_has_two_tables_…` | `…_the_id_counter_…` | + `reservation_ids` (SQLite's sequence), owned by Reservations |
| `test_substitution.py` (2 tests) | same names | The tests-only dict store keeps the grown promise. `scenario` reports a missing record as text, so the bad store is still told apart |
| `test_uml_conformance.py` (6 tests) | same names | The diagram moved to the [P09 class diagram](diagrams/class-diagram.mmd): `next_reservation_id`, `OverlapRejected` (`<<exception>>`), new private members; 18 → 20 lines |
| `test_openapi_contract.py` | + probe `lostTheRace` | Contract 1.2.0; the new example is produced by a real race |
| `practices/P08-…/checks::test_contract_is_1_1_0_with_get_stats` | asks for 1.1 or later | The contract moved to 1.2.0 |

New tests: `tests/test_concurrency.py` (37), the course's two P09 tests in `test_api.py`, and 7 more in
`test_api_sqlite.py`, `test_demo_and_race.py` and `test_substitution.py`. Each concurrency test has
a "control" twin (the version-5 `save`, or the SQLite triggers dropped) that shows the double
booking, so the test is known to be able to fail.

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| PostgreSQL 18 in Docker; `docker compose exec db psql` in two terminals | A throw-away **PostgreSQL 16.15** cluster (initdb, 127.0.0.1, trust) created and deleted by the scripts; the two terminals are two `psql` processes started at fixed offsets, with `pg_sleep` where the sheet says "now switch terminal" and `clock_timestamp()` marks | No Docker daemon here. Btree_gist, EXCLUDE, sequences and the isolation levels behave the same in 16 and 18 | [postgres-repairs](evidence/logs/postgres-repairs.txt); Docker run: **to do by the student** |
| SQLAlchemy + psycopg (`PostgresReservationStore`) | The P07 `SqlReservationStore` (DB-API, `%s` for PostgreSQL), unchanged in shape. Against the real PostgreSQL it ran through [pg_wire.py](evidence/pg_wire.py), a small stdlib protocol client written as **evidence tooling only** (trust auth, extended protocol, psycopg-style `sqlstate`/`diag.constraint_name`) | psycopg cannot be installed (no PyPI) | Two app instances on PostgreSQL in [race-http-before-after](evidence/logs/race-http-before-after.txt); unit tests of the PostgreSQL path with a scripted connection; psycopg on the Mac: **to do by the student** |
| `db/init.sql` (one file) | `db/postgres/init.sql` (the course's file, mounted by compose) + **`db/sqlite/init.sql`** (translation: triggers + one-row id table) | SQLite has no exclusion constraints and no sequences. A drift test keeps the files equal elsewhere | `test_sqlite_and_postgresql_schemas_declare_the_same_tables`, `test_each_postgresql_only_statement_has_its_sqlite_counterpart` |
| Altering the running database by hand in psql | `db/postgres/p09-upgrade.sql` (one transaction) + `db/find-double-bookings.sql`; version-5 SQLite files are upgraded by `main.py` with the same refusal | Repeatable, and the refusal over dirty data is part of the lesson | E11; `test_a_version_5_file_with_a_double_booking_is_not_upgraded_until_it_is_cleaned` |
| Step 1 done before the repair on the student's project | "Before" = a **copy of version 5** (the P08 end state), served with its own wiring and a slow step through `serve.py`, plus version 6 code against PostgreSQL **without** the constraint (the course's Step 1–4 database) | The code change was made in one piece; the old code was kept so "before" is real, not described | [Race results](#race-results) |
| The in-process lock seen only in the list store (`--race`) | Also applied to the web app (`serve.py --app-lock`: one `threading.Lock` per process around each request) and run on one and two instances | Shows the cross-process failure with numbers, not only in words | `v5-lock-1`, `v5-lock-2` |
| `$env:HOTEL_SLOW_STEP` (PowerShell) | `HOTEL_SLOW_STEP=1 python3 main.py` (macOS / Linux) | The student uses macOS | — |
| "19 green: 16 tests + 3 contracts" | 16 unittest tests and **6** contracts (P08's edge contracts kept); full suite 479 | The portfolio adds tests beyond the course's | E17 |
| `lint-imports` | the stdlib ast border test | import-linter not installable | `python -m tests.test_architecture` |

## What was and was not observed

- **Observed on PostgreSQL 16 (psql, concurrent sessions):** the race without a rule; Repeatable Read
  (still double-booked) and Serializable (40001); FOR UPDATE on the reservations locking 0 rows; the
  guard-row wait; the version check (0 rows, retry); a PL/pgSQL trigger letting both rows in; the
  exclusion constraint making Omar's INSERT wait and then fail with 23P01 while his transaction
  survives through the savepoint; the constraint refused over dirty data and accepted after the
  clean-up; a direct INSERT refused; btree_gist required; nextval in two open transactions.
- **Observed on PostgreSQL 16 through the app:** the unchanged `SqlReservationStore` and the
  version-6 wiring in two uvicorn processes, with the race tool (20 rounds + 100 simultaneous pairs),
  without and with the constraint. The driver was `pg_wire.py`, not psycopg.
- **Observed on SQLite:** everything else through `python main.py`, two instances on one file.
- **Not observed here (to do by the student on the Mac):** Docker (PostgreSQL 18, Redis 8),
  `python main.py --db postgres` with psycopg, the two/three real terminals, the commit.

## Check your project (activity sheet §10)

| Check (activity sheet) | What you should see | Seen here | Status |
|---|---|---|---|
| Your checks | 19 green (Python: 16 tests, then 3 contracts) | `Ran 16 tests … OK`; `Contracts: 6 kept, 0 broken.`; pytest 479 passed ([f-unittest](evidence/logs/f-unittest.txt), [f-contracts](evidence/logs/f-contracts.txt), [f-pytest](evidence/logs/f-pytest.txt)) | ✓ Observed |
| `--race` | "Only one guest has R7." | yes ([f-race](evidence/logs/f-race.txt)) | ✓ Observed |
| The race tool, one instance | one 201, one 409 | yes, 20 of 20 rounds, SQLite and PostgreSQL 16 | ✓ Observed |
| The race tool, two instances | the same | yes, 20 of 20 rounds, SQLite and PostgreSQL 16 | ✓ Observed |
| psql: Confirmed reservations for R7 | exactly one | 1 row (SQLite read with sqlite3, PostgreSQL with psql) | ✓ Observed |
| A direct INSERT in psql | refused: `conflicting key value violates exclusion constraint "reservations_no_overlap"` | yes, 23P01 ([postgres-repairs](evidence/logs/postgres-repairs.txt)); SQLite: refused by the trigger (test) | ✓ Observed |
| docs/interleaving.md | your trace and all four repairs with their cost | [interleaving.md](../../hotel-booking/docs/interleaving.md) | ✓ |
| docs/adr-003-booking-concurrency.md | decision, three rejected alternatives, consequences, when to revisit | [ADR-003](../../hotel-booking/docs/adr-003-booking-concurrency.md) (+ Serializable) | ✓ |
| db/init.sql | btree_gist, the named constraint, the id sequence | [db/postgres/init.sql](../../hotel-booking/db/postgres/init.sql) (`test_init_sql_has_btree_gist_the_named_constraint_and_the_sequence`) | ✓ |

## Requirements checklist

Sources: P09 Activity sheet (identical to the Student explanation, Student notes and Presentation
notes apart from the title block, compared with `diff`), the catalog entry (Tue 10 Nov 2026,
room 222), L05 (transaction boundaries, constraints, isolation, optimistic/pessimistic
concurrency), the Python reference (interfaces: `OverlapRejected`, `next_reservation_id`, the
race tool, `HOTEL_SLOW_STEP`/`HOTEL_PORT`, the two tests) and the task brief.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | §1: Docker running, `docker compose up -d` | — | **To do by the student** (no daemon here; local PostgreSQL 16 + redis-server instead) |
| 2 | §1: P08 checks green; reread L05 answers; `# P09 design notes` | E1; l05-notes.md; design-notes § P09 | Done — Observed |
| 3 | Step 1.1: `CREATE SEQUENCE reservation_ids START 101` in init.sql and in the running database (`setval`) | init.sql; p09-upgrade.sql; E5, E11 | Done — Observed (PostgreSQL 16) |
| 4 | Step 1.2: `next_reservation_id` in the contract and both stores; `reserve` uses it | booking.py, internal.py; `test_ids_*`, `test_postgres_ids_come_from_the_sequence` | Done — Observed |
| 5 | Step 1.3: `HOTEL_SLOW_STEP`, `HOTEL_PORT` in the wiring | main.py; `test_slow_step_and_port_come_from_the_environment`; used by E14 | Done — Observed |
| 6 | Step 1.4: the race tool | tools/race_http.py (mypy strict) | Done — Observed |
| 7 | Step 1: race run with `HOTEL_SLOW_STEP=1`, double-booked; rows counted in the database | E3, E4 | Done — Observed |
| 8 | Step 2: interleaving.md: own output, eight-row trace, anomaly + why Repeatable Read does not help, why FOR UPDATE on reservations does not help, four-repairs table | interleaving.md; E6, E7; `test_the_trace_has_eight_rows_and_names_the_anomaly` | Done — Observed |
| 9 | Step 3: list store checks under its lock; `--race` → one guest; table row | internal.py; `test_main_race_flag_gives_r7_to_one_guest`; E8 | Done — Observed |
| 10 | Step 4: second instance (`HOTEL_PORT=5081`), race to both, double booking back; row finished; "where must the rule live" | E3, E8; interleaving.md | Done — Observed |
| 11 | Step 5: guard table, terminal B waits, then refuses; wait in the table | E9 (5 runs, median 0.91 s) | Done — Observed |
| 12 | Step 6: version check: UPDATE 0, rollback, retry refuses; both measurements in the table | E10 | Done — Observed |
| 13 | Step 7.1–7.2: ALTER refused over the double booking, cancel, ALTER accepted | E11; `test_a_version_5_file_with_a_double_booking_is_not_upgraded_until_it_is_cleaned` | Done — Observed |
| 14 | Step 7.3–7.4: btree_gist + named constraint in init.sql | init.sql; checks | Done |
| 15 | Step 7: drop the guard table | It only existed in throw-away experiment databases | Done (n/a to the project schema) |
| 16 | Step 7.5: the store maps 23P01 on `reservations_no_overlap` → `OverlapRejected`; anything else re-raised | `is_overlap_refusal`, `_insert`; `test_postgres_*`, `test_only_the_named_refusal_is_recognised` | Done — Observed (unit + real PostgreSQL via the app) |
| 17 | Step 7.6: `reserve` answers Unavailable | booking.py; `test_a_refused_save_is_answered_unavailable_and_nobody_is_told_confirmed` | Done — Observed |
| 18 | Step 7.7: the two tests; 16 tests green | test_api.py; E17 | Done — Observed |
| 19 | Step 7: direct INSERT refused; race to two instances repaired; constraint row incl. dirty-data clean-up | E12, E14; interleaving.md | Done — Observed |
| 20 | Step 8: ADR-003 with five headings, three rejected repairs with costs, clean-up consequence, revisit condition | adr-003; `test_adr_003_*` | Done |
| 21 | §10: run every check; re-read the ADR; | this table; E17 | Done — Observed |
| 22 | §10: commit "P09: protect the booking rule in the database"; bring the folder to P10; pair work, swap the typist | — | **To do by the student** (no git in this build) |
| 23 | Brief: interleaving with the exact bad interleaving(s) traced step by step | interleaving.md (race and id race), [race-double-booking](diagrams/race-double-booking.svg), [id-allocation](diagrams/id-allocation.svg) | Done — Observed |
| 24 | Brief: protection implemented for BOTH SQLite and PostgreSQL | db/sqlite/init.sql (triggers), db/postgres/init.sql (EXCLUDE), the SQL store for both dialects | Done — Observed |
| 25 | Brief: why an in-process lock alone is not enough across processes | interleaving.md, ADR-003, E8 (0 of 20 vs 20 of 20) | Done — Observed |
| 26 | Brief: safe id allocation, no duplicate-id 500 | `next_reservation_id`; E5; regression `test_a_booking_made_while_another_is_uncommitted_…` | Done — Observed |
| 27 | Brief: race tool run for real before and after, many repetitions | E3, E4, E14–E16 (20 rounds + 100/300 pairs, 12 configurations) | Done — Observed |
| 28 | Brief: conflicts → correct HTTP status in the API and OpenAPI, contract test both ways | 409 (+ deadlock retry so no 500); openapi 1.2.0 `lostTheRace`; E19 | Done — Observed |
| 29 | Brief: ADR-003 in own words with real numbers | adr-003 | Done |
| 30 | Brief: known-defect tests → regression tests; each change documented | [Deliberate test changes](#deliberate-test-changes); E2, E18 | Done — Observed |
| 31 | Brief: the race against real PostgreSQL 16 through concurrent psql sessions; what was / was not observed labelled | E4–E7, E9–E16; [What was and was not observed](#what-was-and-was-not-observed) | Done — Observed (psycopg/Docker: to do, E22) |
| 32 | Brief: other tests green, boundary checks passing | E17 (479 passed, 6 contracts kept, mypy clean, P05–P09 document checks) | Done — Observed |
| 33 | Brief: README (requirement → file, substitutions), worksheet, diagrams (mmdc render-checked), evidence, reflection; root README row | this file, Worksheet.md, diagrams/ + E20, evidence/, reflections/, root README | Done |
| 34 | Brief: stop every server started | the scripts stop uvicorn, redis-server and the PostgreSQL cluster in `finally` blocks; `pgrep` after the runs found none ([f-cleanup](evidence/logs/f-cleanup.txt)) | Done — Observed |

## Self-check before submission

- [x] Exactly one booking wins and the other gets 409, for one and two instances, on SQLite and PostgreSQL (logged runs, not described ones)
- [x] The known-defect tests now assert the correct behaviour; every changed test explains why in its docstring
- [x] Only the named refusal becomes 409; a duplicate id or any other database error is still a fault
- [x] The pre-check is kept; the rule is in the database; the in-process lock is shown failing across processes
- [x] Every number in interleaving.md, ADR-003 and this README comes from a log (the document checks compare them)
- [x] Nothing claims a Docker, psycopg, `lint-imports` or git run that did not happen
