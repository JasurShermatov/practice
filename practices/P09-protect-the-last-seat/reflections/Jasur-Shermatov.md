# Reflection — P09 Protect the last seat

Jasur Shermatov · 23-309 SW

**What I expected.** Since P03 the race had been a pinned "known defect", and I had quietly assumed
that the fix would be a lock around check-then-save. The P09 runs changed that picture. The lock
really works: with one instance not a single round double-booked. Then the same race against two
instances double-booked every round, because each process had its own lock and neither waited for
the other. The lock was written correctly. It was simply in the wrong place.

**What surprised me.**

- The first repair everybody suggests, `SELECT ... FOR UPDATE` on the reservations, locked 0 rows
  on the real PostgreSQL and both bookings went through. You cannot lock a row that does not exist
  yet. After seeing that, "write skew" stopped being a textbook word for me: each request read the
  same empty set and then inserted a different row.
- Repeatable Read did not stop the race either, but Serializable did. It aborted Omar's COMMIT with
  40001. I now know where my L05 answer was right, and also why I still did not pick Serializable:
  every transaction would then need retry handling.
- The id race. Version 5 numbered bookings with `count(*) + 1`. Without the slow step, two
  bookings sent at once to a single version-5 instance mostly ended in **500 duplicate key**, not
  in a double booking. The second bug had been hiding the first one, exactly as the activity sheet
  warned.
- The SQLite translation taught me the most. I first thought "a trigger is SQLite's constraint".
  Then I ran the same trigger logic on PostgreSQL and it let both rows in. The trigger is only safe
  in SQLite because SQLite has one writer at a time. In PostgreSQL the exclusion constraint is
  needed because the index sees the other transaction's undecided row and waits for it. I would not
  have believed this without running it.
- Switching the rule on is a data problem as well as a code problem. The upgrade was refused while
  R101 and R102 both held R7, and somebody has to decide which guest loses the room.

**What I would do differently.** I would make the store own the id from P07 on. I would also write
the concurrency test (threads behind a barrier, so every pre-check happens before any save) before
the fix, and run it against the old code, so that the test is seen failing for the right reason.
I did this here with "control" variants in the tests (the unchecked list store, the dropped
triggers), and it is the part of the test suite I trust most.

**Honest limits.** Two things were not run in this build environment. The PostgreSQL runs went
through a small protocol client that I wrote as evidence tooling, not through psycopg, and Docker
was not running. On my Mac I still have to run `docker compose up -d`, apply `p09-upgrade.sql`
to the existing database and run the race tool with psycopg. The confirmation e-mail is still sent
inside the transaction, so on SQLite it holds the write lock. P10 should take it out of the request.

**Habit to keep.** Reproduce the problem, write the interleaving down, measure each repair, choose
one, and record what it cost. The ADR is the last of these steps.
