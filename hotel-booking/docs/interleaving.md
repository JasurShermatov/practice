# The interleaving that double-books R7

All runs here are **Observed** (Linux container, Python 3.13, SQLite 3.53, PostgreSQL 16.15). The
logs are in [practices/P09-protect-the-last-seat/evidence/logs](../../practices/P09-protect-the-last-seat/evidence/logs/).

## What I ran

`tools/race_http.py` sends two `POST /reservations` for room R7, 2026-11-12 to 2026-11-14: Maya's,
and Omar's 0.5 s later. The app runs with `HOTEL_SLOW_STEP=1`, so every booking waits 1 s between
its check and its save. This was against version 5 (the P08 code) on SQLite, one instance
([race-http-before-after](../../practices/P09-protect-the-last-seat/evidence/logs/race-http-before-after.txt)):

```text
Two bookings for R7, 2026-11-12 to 2026-11-14, sent at the same moment.

Maya -> 201 Created   {"id":"R101","status":"Confirmed","notificationFailed":false}
Omar -> 201 Created   {"id":"R102","status":"Confirmed","notificationFailed":false}

Confirmed reservations for R7 on 12-14 Nov: 2
DOUBLE BOOKED: the room has two confirmed reservations for the same nights.

-- the reservations table, read from the database itself (Confirmed rows for R7):
  id  | room |  check_in  | check_out  |  status
------+------+------------+------------+-----------
 R101 | R7   | 2026-11-12 | 2026-11-14 | Confirmed
 R102 | R7   | 2026-11-12 | 2026-11-14 | Confirmed
(2 rows)
```

It was not a one-off. With `--repeat 20` (accepted bookings cancelled between rounds) version 5 double-booked **20 of 20** rounds with one instance and **20 of 20** with two instances on one SQLite file. The version-6 code on a PostgreSQL 16 database *without* the constraint (the course's database after Step 1) also double-booked **20 of 20** with one and with two instances.

## The interleaving, statement by statement

The same two requests, statement by statement, in two psql sessions on PostgreSQL 16 with the app's
statements and no rule in the table (`race-no-rule` in
[postgres-repairs](../../practices/P09-protect-the-last-seat/evidence/logs/postgres-repairs.txt)).
The times are the server's `clock_timestamp()`. Maya holds her transaction open for 1 s after the
INSERT (the confirmation e-mail is sent there), so this trace also shows the uncommitted row.

| # | Maya's request | Omar's request | What the database holds |
|---|---|---|---|
| 1 | 0.00 s `BEGIN` | | no Confirmed reservation for R7 |
| 2 | 0.00 s overlap check → **0** | | unchanged |
| 3 | | 0.50 s `BEGIN` | unchanged |
| 4 | | 0.50 s overlap check → **0** | unchanged: Maya has inserted nothing yet |
| 5 | 1.00 s `INSERT R101` (id from `nextval`) | | R101 exists, uncommitted and invisible to Omar |
| 6 | | 1.50 s `INSERT R102` - nothing stops it | both rows exist, each invisible to the other |
| 7 | 2.01 s `COMMIT` | | R101 is now visible to everyone |
| 8 | | 2.51 s `COMMIT` | **R101 and R102 are both Confirmed for the same nights** |

Both requests read "no clash", and both were telling the truth when they read it. The gap between
row 2 and row 5 is the whole bug. The check and the save are two separate statements, and another
transaction fits between them. The slow step only widens a gap that is always there. Without it
(both requests sent at once, 100 pairs), version 5 still double-booked **4** pairs with one instance and **11** with two (and answered **63** and **26** second guests with 500, see below). The version-6 code on PostgreSQL without the constraint double-booked **84** and **90** of 100 pairs.

## Which anomaly this is

**Write skew.** Each transaction reads a set of rows (the Confirmed reservations overlapping the
stay), finds it empty, and then **inserts a different row**. Neither overwrites the other's row,
so it is not a lost update. **Repeatable Read does not stop it**, because it only promises that the
rows you read do not change under you, and no row either request read ever changed. Observed: the
same race at `REPEATABLE READ` left two Confirmed rows. `SERIALIZABLE` does stop it. Observed:
Omar's COMMIT failed with `40001 could not serialize access due to read/write dependencies among
transactions`.

## The invariant this breaks

> A room never has two Confirmed reservations covering the same night. (R3; quality scenario S2)

## Why locking the reservation rows cannot fix it

`SELECT ... FOR UPDATE` locks the rows a query returns, and at check time the overlap query returns
none. You cannot lock a row that does not exist yet. Observed with
`SELECT id FROM reservations WHERE room = 'R7' AND status = 'Confirmed' AND <overlap> FOR UPDATE`
in both sessions: "locked 0 rows" twice, nobody waited, and two Confirmed rows. Steps 5 and 6
therefore lock a row that always exists, one guard row per room.

## The second race: the reservation id

Version 5 numbered a booking `R{101 + count(*)}`. With Maya's R101 inserted but not committed, Omar
also counted 0 and also chose R101. His INSERT waited for Maya's transaction and was then refused by
the primary key (`23505 duplicate key value violates unique constraint "reservations_pkey"`,
observed in psql), which the API answered with **500**. Without the slow step this was the most
common outcome against version 5: **63 of 100** simultaneous pairs on one instance and **26 of 100** on two answered the second guest 500 (`UNIQUE constraint failed: reservations.id` in the server log). Since P09 the database hands out the numbers
(`nextval('reservation_ids')`; SQLite: a one-row table updated under its write lock). Observed in
two open transactions: 101 and 102 with no wait, and after Maya's ROLLBACK the next number was 103.
101 was not reused, which leaves a gap but never a duplicate.

## The four repairs, and what each one cost

| Repair | Did it stop the double booking? | What it cost, measured |
|---|---|---|
| In-process lock (Step 3; also applied to the web app: one `threading.Lock` per process around each request) | With one instance, yes (`--race`; web app 0 of 20 rounds (and 0 of 100 simultaneous pairs) double-booked). With two, no: 20 of 20 rounds (and 5 of 100 simultaneous pairs, plus 27 duplicate-id 500s) double-booked | Almost nothing to run, and worth nothing once there are two processes: each has its own lock |
| SELECT ... FOR UPDATE on a guard row (Step 5) | Yes, 1 Confirmed row in every run | Omar **waited 0.91 s** (median of 5 runs: 0.90, 0.91, 0.91, 0.92, 0.90 s) at his `FOR UPDATE` for a room he was never going to get. Every booking for a room queues behind the one in front for its whole transaction |
| Optimistic version check (Step 6) | Yes, 1 Confirmed row in every run | **Nobody waited.** The loser's `UPDATE ... WHERE version = 0` matched 0 rows after **1.00 s** of work (median), which it threw away; it then started again, re-checked and refused. Cheap when clashes are rare, wasteful when they are common |
| Exclusion constraint (Step 7) | Yes, through the app with one and two instances: 0 of 20 on PostgreSQL 16 and SQLite (triggers) | Covers only a rule inside one table. The refusal must be mapped to a readable 409. Omar's INSERT **waited 0.50 s (5 of 5 runs, exactly the time until Maya's COMMIT)** while Maya's row was undecided. It would not switch on until the dirty rows were cleaned up. Simultaneous conflicting INSERTs can deadlock (40P01), which the store now retries (below) |

The two middle repairs are the pessimistic and the optimistic answer to the same question: one
makes the loser **wait**, the other makes the loser **redo**.

**Where does a rule have to live if several processes must obey it?** In the thing they all share
and every writer must pass through, which is the database. A rule guarded by two separate locks is
not guarded at all.

One more observation decided *how* SQLite enforces the rule. SQLite's version is a trigger that
looks for an overlap before the row goes in. The same trigger translated to PL/pgSQL was run on
PostgreSQL (`trigger-in-postgres`) and let **both** rows in: at Read Committed each trigger looked,
saw no committed row and allowed its insert. The trigger is safe in SQLite only because SQLite lets
one connection write at a time, and on SQLite it held in every run (0 double bookings, 8
connections in the tests). PostgreSQL needs the exclusion constraint, because its index sees the
other transaction's *undecided* row and waits for it.

## What it took to turn the constraint on

The constraint could not simply be added. A version-5 database still held the double booking
(R101 and R102, both Confirmed for R7), and `db/postgres/p09-upgrade.sql` was refused:

```text
psql:db/postgres/p09-upgrade.sql:29: ERROR:  could not create exclusion constraint "reservations_no_overlap"
DETAIL:  Key (room, daterange(check_in, check_out, '[)'::text))=(R7, [2026-11-12,2026-11-14)) conflicts with key (room, daterange(check_in, check_out, '[)'::text))=(R7, [2026-11-12,2026-11-14)).
```

`db/find-double-bookings.sql` named the pair. After
`UPDATE reservations SET status = 'Cancelled' WHERE id = 'R102';` the same file printed
`ALTER TABLE`, and the sequence continued at 103. The upgrade runs in one transaction, so the
refused attempt left nothing behind, not even the sequence. A person had to choose which booking to
cancel: in a real hotel somebody would phone one of the two guests. `main.py` refuses to upgrade a
version-5 SQLite file for the same reason, and that is tested.

Without `btree_gist` the constraint cannot be created at all:
`ERROR: data type text has no default operator class for access method "gist"` (observed).

## What running it for real found

The first full run of 100 simultaneous pairs on PostgreSQL with the constraint gave no double
booking, but **1** (one instance) and **6** (two instances) requests were answered **500**. PostgreSQL's log said
`deadlock detected` (40P01). When two conflicting INSERTs reach the exclusion constraint at the same
instant, each can find the other's undecided index entry and wait for it. PostgreSQL then aborts one
of them. The rule held, but the guest got the wrong answer. The store now rolls back to the
savepoint and retries the INSERT, at most 3 times. By the retry the other booking has decided, so
the retry gets either 23P01 (→ 409) or success. Rerun with 300 simultaneous pairs per configuration
([race-http-postgres-after-the-retry](../../practices/P09-protect-the-last-seat/evidence/logs/race-http-postgres-after-the-retry.txt)):
**0 of 300** pairs answered anything but one 201 and one 409, with one and with two instances, while PostgreSQL's log shows **15** and **7** deadlocks that were retried.

## What I kept

The exclusion constraint (in SQLite: its trigger translation), with the pre-check left in front of
it, and ids from the database. The constraint is the only one of the four repairs that no code path
can forget. A new endpoint, a background job, a migration script, a second instance or somebody
typing `INSERT` into psql all hit it (observed: `23P01` for a direct INSERT). The pre-check stays so
that the ordinary case still gets a clean `409 Unavailable` without the app having to explain a
database error. The decision is recorded in [ADR-003](adr-003-booking-concurrency.md).
