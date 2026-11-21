# Observed runs — P09

These are condensed excerpts. The full outputs are in [logs/](logs/), and the labels and limits
are in [Index.md](Index.md). Environment: Linux container, Python 3.13.18, SQLite 3.53.1,
PostgreSQL 16.15 (a throw-away cluster), redis-server 7.0.15.

## O1 · Before: the race tool against version 5 (E3)

`race_experiment.py` started the version-5 copy with its own wiring (`serve.py`, slow step 1 s) and
ran the project's `tools/race_http.py` ([race-http-before-after](logs/race-http-before-after.txt)):

```text
Maya -> 201 Created   {"id":"R101","status":"Confirmed","notificationFailed":false}
Omar -> 201 Created   {"id":"R102","status":"Confirmed","notificationFailed":false}
Confirmed reservations for R7 on 12-14 Nov: 2
DOUBLE BOOKED: the room has two confirmed reservations for the same nights.
 R101 | R7   | 2026-11-12 | 2026-11-14 | Confirmed
 R102 | R7   | 2026-11-12 | 2026-11-14 | Confirmed
Double bookings: 20 of 20 rounds; one 201 and one 409: 0; anything else: 0.
```

With no slow step and both requests sent at once (100 pairs), one instance gave 4 double bookings
and 63 × 500. The server log showed `sqlite3.IntegrityError: UNIQUE constraint failed: reservations.id`,
which is the duplicate R101.

## O2 · After: version 6, two instances, SQLite (E14)

`HOTEL_SLOW_STEP=… HOTEL_PORT=… python main.py` twice, then `python tools/race_http.py <second instance>`:

```text
Maya -> http://localhost:5080   Omar -> http://localhost:5081
Maya -> 201 Created   {"id":"R101","status":"Confirmed","notificationFailed":false}
Omar -> 409 Conflict  {"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}
Confirmed reservations for R7 on 12-14 Nov: 1
CORRECT: one booking was accepted and one was refused.
 R101 | R7   | 2026-11-12 | 2026-11-14 | Confirmed
(1 row)
Double bookings: 0 of 20 rounds; one 201 and one 409: 20; anything else: 0.
-- ids handed out by the database: 42; ... refused by the database itself (lost the race): 21
```

## O3 · The in-process lock across processes (E8)

```text
STEP 3 - version 5 + an in-process lock around every request, ONE instance   -> Double bookings: 0 of 20 rounds
STEP 4 - version 5 + the same in-process lock, TWO instances               -> Double bookings: 20 of 20 rounds
```

## O4 · The interleaving and the isolation levels on PostgreSQL 16 (E6, E7)

[postgres-repairs](logs/postgres-repairs.txt). Server timestamps, relative to the first step:

```text
race-no-rule:      0.00 Maya check 0 | 0.50 Omar check 0 | 1.00 Maya INSERT R101 | 1.50 Omar INSERT R102 | 2.01 / 2.51 COMMIT -> 2 rows
repeatable-read:   ... the same ... -> 2 rows
serializable:      2.51s  Omar   COMMIT failed: 40001 could not serialize access due to read/write dependencies among transactions
lock-the-reservations: FOR UPDATE on overlapping reservations locked 0 rows (both) -> 2 rows
trigger-in-postgres:   both INSERTs passed the PL/pgSQL trigger -> 2 rows
ids-from-count:    2.01s  Omar   INSERT refused: 23505 duplicate key value violates unique constraint "reservations_pkey"
ids-from-sequence: nextval -> 101 | (Maya not committed) nextval -> 102 | after Maya's ROLLBACK: nextval -> 103
```

## O5 · Guard row and version check (E9, E10)

```text
  0.11s  Omar   SELECT ... FOR UPDATE asked
  1.00s  Maya   INSERT R101
  1.01s  Omar   SELECT ... FOR UPDATE returned: holds the lock on R7
  1.01s  Omar   overlap check sees 1
Omar's wait at FOR UPDATE, 5 runs (s): 0.90, 0.91, 0.91, 0.92, 0.90; median 0.91 s.

  0.10s  Omar   UPDATE ... WHERE version = 0 matched 1 row(s)
  1.00s  Maya   UPDATE ... WHERE version = 0 matched 0 row(s)
  1.00s  Maya   ROLLBACK, then try again from the start
  1.01s  Maya   overlap check sees 1
```

## O6 · The exclusion constraint (E11, E12)

```text
  1.50s  Omar   INSERT asked
  2.01s  Maya   COMMIT done
  2.01s  Omar   INSERT refused: 23P01 conflicting key value violates exclusion constraint "reservations_no_overlap"
  2.01s  Omar   COMMIT done           (the savepoint kept his transaction usable)

$ psql -v ON_ERROR_STOP=1 -f db/postgres/p09-upgrade.sql      (version-5 data with R101 + R102)
ERROR:  could not create exclusion constraint "reservations_no_overlap"
$ psql -c "UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102';"
$ psql -v ON_ERROR_STOP=1 -f db/postgres/p09-upgrade.sql
ALTER TABLE

-- a direct INSERT for 13-15 Nov
ERROR:  23P01: conflicting key value violates exclusion constraint "reservations_no_overlap"
CONSTRAINT NAME:  reservations_no_overlap
```

## O7 · The deadlock found by the burst, and the fix (E15, E16)

The first run with 100 simultaneous pairs on PostgreSQL with the constraint:
`0 / 1 (of 100)` and `0 / 6 (of 100)`, which means no double booking, but 500 answers.
The server logs said `pg_wire.PgError: deadlock detected`. After the bounded retry in
`SqlReservationStore._insert`
([race-http-postgres-after-the-retry](logs/race-http-postgres-after-the-retry.txt)):

```text
Double bookings: 0 of 300 rounds; one 201 and one 409: 300; anything else: 0.
-- PostgreSQL's own log for this phase: 275 x 23P01 reservations_no_overlap, 15 x 40P01 deadlock detected
Double bookings: 0 of 300 rounds; one 201 and one 409: 300; anything else: 0.      (two instances)
-- PostgreSQL's own log for this phase: 268 x 23P01 reservations_no_overlap, 7 x 40P01 deadlock detected
```

## O8 · Tests, mutations, diagrams (E17, E18, E20)

```text
python3 -m unittest            Ran 16 tests ... OK
python3 -m pytest              479 passed
python3 -m tests.test_architecture   Contracts: 6 kept, 0 broken.
python3 -m mypy                Success: no issues found in 33 source files
break_the_fix.py               9 of 9 mutations caught by the test suite.
render_diagrams.sh             9 x exit 0
```
