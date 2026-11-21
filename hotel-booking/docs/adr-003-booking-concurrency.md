# ADR-003: Protect the booking rule in the database

- Status: accepted (P09)
- Session: Tuesday 10 November 2026 (P09 — Protect the last seat)
- Extends ADR-001 (one program, four modules) and ADR-002 (the search cache, which booking never reads).

## Context

R3 says that a room never has two Confirmed reservations covering the same night. From P03 to P08
the rule lived only in `BookingService.reserve`, which asks `has_overlap` and then saves. One
request at a time, it holds. Two requests at the same moment can both read "free", both insert and
both commit. That is a double booking, and the race tool produced one in **20 of 20** rounds
against version 5. The trace is in [interleaving.md](interleaving.md). The anomaly is write
skew: each transaction reads the same empty set and inserts a different row. Because no row that
either of them read is changed, Repeatable Read does not stop it (observed). `SELECT ... FOR UPDATE`
on the reservations does not stop it either, because at check time there is no row to lock
(observed: "locked 0 rows"). `docs/capacity.md` already plans for a second app instance, so the
repair has to hold across processes.

A second race was hiding behind the first. Ids came from `count(*) + 1`, so two requests could
both call their booking R101 and the second failed with a primary-key error, which the API
answered with 500. Without the slow step that was the most common outcome against version 5
(63 of 100 simultaneous pairs answered 500 on one instance).

## Decision

1. **The rule lives in the table.** On PostgreSQL it is an exclusion constraint:

   ```sql
   CREATE EXTENSION IF NOT EXISTS btree_gist;

   ALTER TABLE reservations
       ADD CONSTRAINT reservations_no_overlap
       EXCLUDE USING gist (
           room WITH =,
           daterange(check_in, check_out, '[)') WITH &&
       ) WHERE (status = 'Confirmed');
   ```

   It is in `db/postgres/init.sql` for new databases and in `db/postgres/p09-upgrade.sql` for the
   running one. SQLite, the default and test database here, has no exclusion constraints. It gets
   two triggers with the same name (`db/sqlite/init.sql`) that refuse the row. That is atomic in
   SQLite only because SQLite lets one connection write at a time. The same trigger on PostgreSQL
   let a double booking through (observed), which is why PostgreSQL gets the constraint.
2. **The store's promise grows.** `ReservationStore.save` raises `OverlapRejected` instead of
   writing a second Confirmed reservation for a room-night. `SqlReservationStore` recognises only
   that refusal: SQLSTATE 23P01 plus the name `reservations_no_overlap`, or SQLite's trigger error
   plus the name. Everything else, such as a duplicate id, is re-raised. On PostgreSQL the INSERT
   runs inside a savepoint, so the refusal does not abort the request's transaction. The list store
   keeps the same promise with a check under its lock, which lets the course's two tests run
   without a database.
3. **The pre-check stays in front.** `reserve` still asks `has_overlap` first, because it answers the
   ordinary case cheaply and readably. When the store refuses, `reserve` answers the same
   `Unavailable`, the API answers the same `409` with the same body, and contract 1.2.0 documents
   it.
4. **Ids come from the database.** This is `next_reservation_id()`: `nextval('reservation_ids')` on
   PostgreSQL, and `UPDATE reservation_ids ... RETURNING` on a one-row table in SQLite.

## Alternatives considered

**An in-process lock.** This is a `threading.Lock` around check-then-save. It works within one
process: with the lock around every request, one instance gave 0 of 20 double bookings. With two
instances it gave **20 of 20 rounds double-booked**, because each process has its own lock and neither waits for the
other. On top of that, the real app's SQL store was never behind the list store's lock. Rejected,
because ADR-001 and `capacity.md` expect more than one instance.

**`SELECT ... FOR UPDATE` on a guard row.** This means one `room_booking_guard` row per room, locked
at the start of every booking. It is correct (one Confirmed row in every run). The cost was
measured on PostgreSQL 16: Omar waited **0.91 s** (median of 5 runs) at the lock for a room he
was never going to get, and every booking for a room queues behind the one in front for the whole
transaction, including the confirmation e-mail that is still inside it (P10). Each booking would
also need to remember to take the lock, and a guard row must exist for every room, including rooms
added later. This is the right tool when a rule spans tables. Rejected here.

**Optimistic version checking.** The same guard row with a `version` column, where the write is
`UPDATE ... WHERE version = <read>`, and 0 rows matched means somebody else won. It is correct, and
nobody waits. Its cost is measured as redo: the loser had already spent **1.00 s** of work before
its `UPDATE` matched 0 rows, then rolled back and had to repeat the check. Every write path needs
the version dance and a bounded retry loop, and the rule is still kept only by code that remembers
to do it. Rejected.

**Serializable isolation.** This is correct and needs no schema change. Observed: Omar's COMMIT
failed with `40001 could not serialize access due to read/write dependencies among transactions`.
Rejected for now, because every transaction in the app would then need to expect serialization
failures and retry, which is a larger change than this one rule needs. Worth revisiting if a second
write-skew rule appears.

## Consequences

- The rule is true whoever writes. Both instances of the app, a direct `INSERT` typed into psql
  (refused with 23P01, observed) and any future endpoint or job go through it. After the change the
  race tool gave **0 of 20 rounds (and 0 of 100-300 simultaneous pairs)** double bookings in every configuration.
- A booking can now fail at the INSERT. The store maps that to `OverlapRejected`, and the API to
  409. Tests cover this on the list store, on SQLite with 8 connections, and on the PostgreSQL path
  with a scripted connection. The real PostgreSQL ran it through the app as well (see evidence).
- On PostgreSQL the loser's INSERT **waits** while the winner's row is undecided (observed
  0.50 s), then fails. The wait lasts only as long as the winner's transaction. Two conflicting
  INSERTs at the same instant can instead **deadlock** (40P01). The first 100-pair run answered 1
  and 6 of those requests with 500, so the store now retries the INSERT from its savepoint (at most
  3 times). Rerun with 300 pairs: 15 and 7 deadlocks, all retried, 0 answered 500.
- **The constraint could not be added until the duplicate rows were cleaned up.** Over the version-5
  data PostgreSQL refused `ADD CONSTRAINT` (`could not create exclusion constraint`). One of R101
  and R102 had to be cancelled first: R102 was cancelled. `main.py` refuses to upgrade a version-5
  SQLite file for the same reason. A person decides which booking stays. In a real hotel somebody
  would phone a guest.
- The constraint only covers a rule inside the `reservations` table.
- Writing a reservation also maintains a GiST index. At the capacity in `capacity.md` (20 bookings
  a day) this does not show.
- Ids can have gaps (a refused booking uses up its number). Ids are never given out twice.
- `db/postgres/init.sql` and the running database must both be changed. The upgrade file does it
  once, in one transaction.

## When to revisit

- A second rule needs protecting that does not fit in one table, for example a booking together
  with its deposit in P17. That would mean a guard-row lock or Serializable.
- Bookings become frequent enough for the GiST index writes, or the loser's wait, to show up in a
  measurement.
- Reservations start being written by more than one service. At that point the constraint is the
  only thing every writer shares.
