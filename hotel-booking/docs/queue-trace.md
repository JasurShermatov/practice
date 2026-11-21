# The confirmation email, taken out of the request

P10, hotel-booking version 7. Every output below is **Observed**: it was copied from
[queue-experiment.txt](../../practices/P10-bounded-async-processing/evidence/logs/queue-experiment.txt).
Environment: Linux container, Python 3.13.18, SQLite 3.53.1, redis-server 7.0.15 for the search
cache, PostgreSQL 16.15 for the last section. Each server is `python main.py` in its own process on
a fresh database file. The client is `tools/burst.py` in a second process, which sends the bookings
one after another (R7 and R8, one night each from 1 December). Every booking is legal, so whatever
is refused below was refused by the notification queue and not by the booking rule. "The worker" is
one thread unless `HOTEL_WORKERS` says otherwise. The one-second mail server is
`HOTEL_EMAIL_SECONDS=1`.

## What the email was costing the guest

`HOTEL_EMAIL_SECONDS=1 python main.py --no-queue` keeps the P09 behaviour: the confirmation is sent
inside the request, after the INSERT and before the COMMIT.

```text
Sending 1 bookings, one after another...

Accepted: 1
Rejected: 0
Slowest booking: 1.04 s
Total: 1.0 s
```

The booking itself is three database questions (`databaseQueries: 3`). Measured over HTTP on the
same machine, such a booking takes about 3 ms (the queued runs below). The rest of the 1.04 s was
the mail server, and the guest waited for it although the room was already theirs.

Thirty of them, one after another:

```text
Sending 30 bookings, one after another...

Accepted: 30
Rejected: 0
Slowest booking: 1.04 s
Total: 30.2 s

GET /stats
{"searches":0,"databaseQueries":90,"cacheHits":0,"cacheMisses":0,"cacheErrors":0}

Booking latency: p50 1004.8 ms, p95 1005.7 ms, max 1037.1 ms
```

That is 30.2 seconds to do about 0.1 s of work. With SQLite there is a second cost: the write lock
is held from the INSERT to the COMMIT, so every other booking also waited for that mail server.

## With a queue in front of the sender

The same booking against `HOTEL_EMAIL_SECONDS=1 python main.py` (queue of 10, one worker):

```text
Sending 1 bookings, one after another...

Accepted: 1
Rejected: 0
Slowest booking: 35 ms
Total: 0.0 s

GET /stats
{...,"notificationsAccepted":1,"notificationsRejected":0,"notificationsCompleted":0,"notificationsQueued":0,"notificationsFailed":0}

GET /stats, 1.0 seconds later
{...,"notificationsAccepted":1,"notificationsRejected":0,"notificationsCompleted":1,"notificationsQueued":0,"notificationsFailed":0}
```

The answer came before the email. At the moment of the first GET /stats the job was *in flight*:
the worker had taken it off the queue (`queued 0`) and had not finished it (`completed 0`). One
second later it was sent. The 35 ms is the first request of a fresh process. In the bursts below the
same booking has a median of 3.4 ms and a 95th percentile of 6.5 ms, so the booking request went from
**1.04 s to a few milliseconds**.

Two things are different from simply moving the call to a thread:

- The confirmation only **holds a place** in the queue while the booking's transaction is open.
  The worker gets it **after the COMMIT** (`HeldConfirmations.publish`), so a guest is never
  emailed about a booking that rolled back
  (`tests/test_queue_wiring.py::test_a_booking_that_rolls_back_is_never_emailed`), and the worker
  always finds the row committed (`test_the_worker_only_ever_sees_committed_bookings`, 20 of 20).
- `BookingService` did not change. It still calls `send_confirmation` once, after the save. The
  wiring decides what that call does.

## Why an unbounded queue is not the answer

`HOTEL_EMAIL_SECONDS=1 HOTEL_QUEUE_CAPACITY=10000 python main.py`:

```text
Sending 30 bookings, one after another...

Accepted: 30
Rejected: 0
Slowest booking: 39 ms
Total: 0.2 s

GET /stats
{"searches":0,"databaseQueries":90,"cacheHits":0,"cacheMisses":0,"cacheErrors":0,"notificationsAccepted":30,"notificationsRejected":0,"notificationsCompleted":0,"notificationsQueued":29,"notificationsFailed":0}
```

My three numbers: **accepted 30, rejected 0, queued 29** (plus one in flight). Every guest was
answered at once, and 29 emails sat in memory waiting for a worker that sends one per second.

What a burst of thirty thousand would do (measured in-process,
[unbounded-30000.txt](../../practices/P10-bounded-async-processing/evidence/logs/unbounded-30000.txt)):
all 30,000 were accepted in 1.26 s, the queue held **9.8 MB** (327 bytes per job), and one worker
would need **8.3 hours** to send them. Nothing refused them. If the burst is bigger or never stops,
memory grows until the process dies, and it takes the bookings down with the emails. The queue has
no limit of its own, so the limit becomes the machine.

When that server was stopped (Ctrl+C, drain limited to 3 s for the experiment), the cost became
visible:

```text
Stopping the app with 30 confirmations accepted and 1 sent so far...
Draining the notification queue: 29 to go (at most 3 s)
Notification workers stopped after 3.7 s.
accepted=30  rejected=0  completed=5  failed=0  dropped=25  queued=0  in_flight=0
25 guests are owed an email that will not be sent: R106, R107, R108, ... R130
```

The database held 30 Confirmed reservations. Twenty-five of those guests will never hear about theirs.

## With a bound, and counted rejections

`HOTEL_EMAIL_SECONDS=1 python main.py` (the default bound of 10, one worker):

```text
Sending 30 bookings, one after another...

Accepted: 30
Rejected: 0
Slowest booking: 37 ms
Total: 0.1 s

GET /stats
{"searches":0,"databaseQueries":90,"cacheHits":0,"cacheMisses":0,"cacheErrors":0,"notificationsAccepted":11,"notificationsRejected":19,"notificationsCompleted":0,"notificationsQueued":10,"notificationsFailed":0}

Booking latency: p50 3.4 ms, p95 6.5 ms, max 36.9 ms
Answers with notificationFailed: true: 19
```

All 30 bookings were accepted and all 30 rows are in the database. 19 confirmation emails were
refused on purpose because the queue was full, and each of those 19 guests was told so in the answer
(`notificationFailed: true`). The 11/19 split is the course's HTTP split: the worker took job 1 right
away and freed one place. Five more fresh runs gave the same split every time: 11/19/10, p50
3.4–4.4 ms, p95 5.6–22.9 ms, total 0.14–0.26 s.

The queue depth after the burst, read every half second (from the log):

| t after the burst | 0.0 s | 1.0 s | 2.0 s | 3.0 s | 4.0 s | 5.0 s | 6.0 s | 7.0 s | 8.0 s | 9.0 s | 10.05 s | 11.05 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| queued | 10 | 9 | 8 | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 | 0 |
| completed | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |

And once the worker had caught up:

```text
GET /stats, 11.1 seconds later
{"searches":0,"databaseQueries":90,"cacheHits":0,"cacheMisses":0,"cacheErrors":0,"notificationsAccepted":11,"notificationsRejected":19,"notificationsCompleted":11,"notificationsQueued":0,"notificationsFailed":0}
```

accepted 11 = completed 11 + failed 0 + queued 0, so everything the queue took, it finished. The
three things that are always true, each checked by a test:

1. `queued` never goes above the bound (`test_the_bound_holds_and_the_sums_balance_under_many_producers`:
   8 producer threads and 3 workers, read 200 times).
2. Every booking succeeds. A refused email is not a refused room (`test_a_full_queue_never_fails_a_booking`).
3. accepted = completed + failed + dropped + queued + in flight, with at most one job in flight per worker.

**What rejected above zero in normal running tells me:** the mail server, the worker count or the
bound is wrong for the traffic. `queued` and the drain time say which one. A rejection is acceptable
only during a real burst.

### Workers: what the bound decides and what the workers decide

`tools/burst.py --wait` waits until every accepted job has ended and prints the drain time and the
emails per second:

| Run | HOTEL_WORKERS | Accepted / rejected | Drained after the burst | Emails per second |
|---|---|---|---|---|
| 1 s sender, bound 10, burst 30 | 1 | 11 / 19 | 10.9 s | 0.99 |
| 1 s sender, bound 10, burst 30 | 2 | 12 / 18 | 5.9 s | 1.98 |
| 1 s sender, bound 10, burst 30 | 4 | 14 / 16 | 3.9 s | 3.44 |
| 0.2 s sender, bound 100, burst 50 | 1 | 50 / 0 | 9.9 s | 4.95 |
| 0.2 s sender, bound 100, burst 50 | 2 | 50 / 0 | 4.8 s | 9.90 |
| 0.2 s sender, bound 100, burst 50 | 4 | 50 / 0 | 2.5 s | 18.75 |

The bound decides what is accepted: bound + one job per worker in flight, so 11, 12 and 14. The
workers decide how fast it is finished, and throughput grows with them almost linearly because the
work is waiting on I/O. The booking latency did not move (p50 2.8–3.5 ms in every row).

### When the mail server fails or hangs

| Run | Result | Drained after |
|---|---|---|
| every 3rd attempt fails, `HOTEL_SEND_ATTEMPTS=1` (no retry, the course's policy) | completed 20, **failed 10**, each logged: `confirmation for R103 failed after 1 attempt(s): ...` | 1.5 s |
| the same, `HOTEL_SEND_ATTEMPTS=3` (backoff 0.5 s, then 1 s) | completed 30, failed 0 | 9.1 s |
| the mail server would take 5 s, `HOTEL_EMAIL_TIMEOUT=0.5` | **failed 4**, each after 0.5 s; the worker moved on | 2.0 s |

In every run all bookings were 201 and saved. A failure later, in a worker, cannot change an answer
the guest already has. It is counted (`notificationsFailed`), recorded (`DeliveryStatus.FAILED`) and
logged with the reservation id. A retry takes place inside the same worker and never back on the
queue, so it cannot take a waiting guest's place. The queue never sends a job twice: 300 jobs, 4
workers and one failure each gave 300 sends to 300 different ids
(`test_many_workers_and_retries_still_send_every_email_exactly_once`). If a send *times out* after
the mail server has in fact accepted it, a retry could make a second email at the mail server. That
is one reason the default is no retry.

## The numbers, and what each one means

| Counter (GET /stats) | What it counts | What it tells you |
|---|---|---|
| notificationsAccepted | jobs the queue took (after the booking committed) | how much work the app promised to do |
| notificationsRejected | jobs refused because the queue was full or closing | how much it refused to promise: visible, countable, deliberate, and also in each answer |
| notificationsCompleted | jobs the workers finished | how much it actually did |
| notificationsQueued | jobs waiting right now | how far behind the workers are; never above the bound |
| notificationsFailed | jobs given up after every allowed attempt (portfolio addition) | work that was tried and lost, with a log line for each |

The invariant to check is accepted = completed + failed + queued **once nothing is in flight**. A
worker that is part-way through a send has taken the job off the queue and has not finished it, so
the two sides may differ by up to one job per worker. The course's version leaves a failed send
uncounted, so the sides stop balancing. I count it as `failed` instead, so a failure is never
confused with a loss. Only a job that disappears in neither way would break the balance.

## What a rejected email is, and is not

A rejected email is **not** a failed booking. All 30 guests got their rooms, and 19 of them did not
get a confirmation. That separation is deliberate, and it is the R6 rule from P04 again: the booking
is already saved, so a failed message must not undo it or hide it. The 201 answer says
`notificationFailed: true`, so the website (or the receptionist) knows which guests to tell some other
way.

It is also not free. Nineteen guests have a reservation that nobody emailed them about. That is
tolerable only because the number is counted and visible in two places. A queue that silently dropped
them would look exactly like a queue that was coping.

## What stopping the app does

Ten bookings with the one-second sender, then the stop signal about 2.6 s later (2 sent, 7 queued,
1 in flight).

**Ctrl+C, with the drain (the default):**

```text
Stopping the app with 10 confirmations accepted and 2 sent so far...
Draining the notification queue: 8 to go (at most 30 s)
Notification workers stopped after 7.3 s.
accepted=10  rejected=0  completed=10  failed=0  dropped=0  queued=0  in_flight=0
Nobody was owed an email.
```

**SIGTERM** (what Docker and most deploys send) printed the same: 10 of 10 sent, after 7.2 s. This
needed the drain to sit in the app's shutdown hook. uvicorn re-raises SIGTERM after its own shutdown,
so code placed after `uvicorn.run` never runs for it
(`test_the_real_server_drains_its_queue_when_it_is_stopped[sigterm]`).

**Without the drain** (`--no-drain`):

```text
Stopping the app with 10 confirmations accepted and 2 sent so far...
(no drain) 8 confirmations are queued or being sent
Notification workers stopped after 0.2 s.
accepted=10  rejected=0  completed=3  failed=0  dropped=7  queued=0  in_flight=0
7 guests are owed an email that will not be sent: R104, R105, R106, R107, R108, R109, R110
```

The course's version leaves the seven on the queue: there, `accepted == completed + queued` is still
true at the last reading, and the jobs vanish a second later when the process exits, with no trace.
Mine cancels them explicitly, so the counters say `dropped=7` and the log names every guest. This
helps the person who reads the log. It does not send the emails.

The drain also has a limit (`HOTEL_DRAIN_SECONDS`, 30 s by default). A queue that is still being
filled would never empty and the deploy would hang. So the app stops accepting first (new
confirmations are rejected from the first moment), drains until the limit, and then says what it
dropped. The unbounded run above is that case: 3 s, 5 sent, 25 named.

**kill -9:**

```text
(nothing - the process was killed; no shutdown code ran)
Confirmed rows in the database afterwards: 10
```

Ten reservations are in the database. Two emails were sent, one may have been part-way through, and
seven were on the queue. Nothing printed, no counter changed, and no log line says that anyone is
owed an email.

## What this design still loses

The queue is in memory, and the reservation is not. A polite stop (Ctrl+C, SIGTERM, a normal deploy)
drains the queue within its time limit and names anyone still owed. A killed process (`kill -9`, an
out-of-memory kill, a crashed container, a power cut) loses every queued confirmation, and nothing
anywhere records how many there were. The booking survives and the job does not. The bound does not
fix this: it only keeps the loss to at most 10 jobs plus one per worker. The counters do not fix it
either: they die with the process.

The honest fix is a durable queue: write the job into the database **in the same transaction as the
booking**, so the reservation and its confirmation are saved or lost together, and let the worker
read the jobs from there. That is the **transactional outbox, and P17 builds it**. Until then, the
bound, the counters, the `notificationFailed` answer and the shutdown log make the loss visible, and
that is all they buy.

## The same on PostgreSQL, and P09 still holds

On a throw-away PostgreSQL 16.15 cluster (`db/postgres/init.sql` with the exclusion constraint;
driver: P09's `pg_wire` in place of psycopg), the same bounded burst gave **11 accepted / 19
rejected / 10 queued**, booking latency p50 9.1 ms and p95 31.2 ms, 30 Confirmed rows in psql, and
`completed 11` after 10.7 s. The race tool with `HOTEL_SLOW_STEP=1 HOTEL_EMAIL_SECONDS=1` gave
**0 double bookings in 20 of 20 rounds** in three setups: one SQLite instance, two SQLite instances
on one file, and two PostgreSQL instances on one database. psql found no room with two Confirmed
reservations. The race's loser is refused before any email is held, so only the winner is emailed
(`test_the_race_still_gives_the_room_to_one_guest_and_one_email`).
