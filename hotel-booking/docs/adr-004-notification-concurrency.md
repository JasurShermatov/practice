# ADR-004: Send confirmation emails from a bounded queue with a fixed number of workers

- Status: accepted (P10, hotel-booking version 7)
- Session: Saturday 14 November 2026 (P10 — Bounded async processing)
- Extends: ADR-003 (the booking rule stays in the database; nothing here touches it).
  Superseded later by: the transactional outbox (P17), for durability only.
- Evidence: [queue-trace.md](queue-trace.md) and
  [queue-experiment.txt](../../practices/P10-bounded-async-processing/evidence/logs/queue-experiment.txt) (all Observed)

## Context

The confirmation email was sent inside the booking request, after the INSERT and before the COMMIT.
With a mail server that takes one second (`HOTEL_EMAIL_SECONDS=1`), one booking took **1.04 s**, and
thirty bookings one after another took **30.2 s**. The booking itself, three database questions,
takes about **3 ms** over HTTP. The guest waited for a message about a room that was already theirs.
On SQLite every other booking waited as well, because the write lock is held until the COMMIT. A mail
server that is *down* rather than slow would make a successful booking look like a failed one.

Taking the email out of the request needs somewhere to keep it, and the first answer, an unbounded
queue, swaps a slow request for unbounded memory. A burst of 30 left **29 jobs** in memory and
refused nothing. A burst of 30,000, measured in-process, was all accepted: **9.8 MB**, and **8.3
hours** of work for one worker. The limit was the machine, and nobody chose it.

The work itself has four properties that decide its shape:

1. The request **causes** it but does not **own** it. The answer does not depend on it, and it must
   outlive the request.
2. It is **one stage**: send one message.
3. **Nobody waits** for its result, and it is not part of a larger computation.
4. It shares **no mutable state** with the booking, only an immutable `Confirmation` (five plain
   values). The consumer (the mail server) can be slower than the producer (bookings), so it **needs
   a limit**.

## Decision

Send confirmations from a **bounded in-memory queue drained by a fixed pool of worker threads**,
owned by the Notifications module (`QueuedNotificationSender` in `notifications/internal.py`).

- **Bound: 10** (`HOTEL_QUEUE_CAPACITY`). **Workers: 1** (`HOTEL_WORKERS`). Both were chosen against the
  measurement: a burst of 30 against a one-second sender accepted 11 and finished them in 11 s. More
  workers drain faster (2 workers: 5.9 s, 4 workers: 3.9 s) without changing the booking latency.
- **When the queue is full a confirmation is refused and counted, never waited for.** A full queue has
  three options. Making the request wait is what this design exists to remove. Dropping an older
  job is wrong because a confirmation is not superseded by a newer one. So the third option, refusing
  the newest job, is the one taken. The refusal is counted (`notificationsRejected`), recorded
  (`DeliveryStatus.REJECTED`), logged with the reservation id, and returned to the guest's client as
  `notificationFailed: true`. **The booking always succeeds** (201, row saved): 30 of 30 under the
  burst.
- **The confirmation reaches the queue only after the COMMIT.** Inside the transaction it only
  *holds a place* (`HeldConfirmations`), so a full queue is known before the answer is sent. A
  rollback gives the place back, so no guest is emailed about a booking that does not exist, and a
  worker never sends before the row is committed.
- **Counters on GET /stats:** `notificationsAccepted`, `notificationsRejected`,
  `notificationsCompleted` and `notificationsQueued` (the course's four), plus `notificationsFailed`.
  Once nothing is in flight, accepted = completed + failed + queued. Contract 1.3.0, all five optional.
- **Retry policy:** `HOTEL_SEND_ATTEMPTS`, **default 1 (no retry)**. When it is raised, a failed send is
  retried inside the same worker with a doubling delay (0.5 s, 1 s, ...) and never put back on the
  queue. Each send is bounded by the sender's own timeout (`HOTEL_EMAIL_TIMEOUT`, 10 s).
- **Shutdown:** the shutdown hook (Ctrl+C or SIGTERM) stops accepting at once, drains for at most
  `HOTEL_DRAIN_SECONDS` (30 s), stops the workers (a waiting retry is cancelled), and drops and
  **names** whatever is left. Measured: 10 of 10 sent after 7.3 s (Ctrl+C) and 7.2 s (SIGTERM).
- **One owner of the concurrency:** the queue is the only place in the package that starts threads
  (checked by `tests/test_architecture.py`). The wiring creates it and the shutdown hook closes it.
  A new border contract keeps Notifications a leaf ("Notifications depends on no other module").

## Alternatives considered

Each reason below is about the work, not about a library.

**No queue: keep sending inside the request.** This is the simplest option, and the measurement
already rejected it: every guest waits for the mail server (1.04 s per booking, 30.2 s for 30), and a
mail server outage looks like a booking outage. The request does not own this work, so it should not
wait for it.

**An unbounded queue.** It is one argument shorter than a bounded one. It cannot answer the question
"what happens when the consumer is slower than the producer for long enough?". Measured: 29 jobs
waiting after 30 bookings, 9.8 MB and 8.3 hours of work after 30,000, nothing refused. Rejected:
*the work needs a limit*, and without one the limit is the machine, chosen by accident.

**An actor per room.** One mailbox per room, with messages handled one at a time. It would also put
each room's bookings in a single line, which means moving the booking rule out of the database. ADR-003
has just decided against that, because the rule must hold across instances. For the email it is far
more machinery than one message needs. Rejected: *there is no per-room state to protect here*, so
the email does not need a mailbox per room.

**A reactive pipeline.** Backpressure is part of the protocol instead of being added on, and that
works well when there are many stages with demand flowing between them. Rejected for now: *there is
one stage*. One bounded queue already gives the backpressure that one stage needs.

**Fork-join / parallel streams.** Wrong shape twice over. Fork-join splits one piece of work into
parts and waits for all of them. *The email is not part of the booking, and nobody waits for it.*

**Structured concurrency.** The right default for work a request owns, because a child task cannot
outlive the scope that started it. That is exactly why it does not fit: *the email must outlive the
request.* It would bring back the one-second wait.

**Software transactional memory.** It composes changes to shared in-memory state without locks.
*There is no shared mutable state to compose.* The only shared thing is the queue, and it is already
thread-safe. The `Confirmation` is immutable.

**asyncio tasks on the event loop (an implementation alternative).** The sender is blocking I/O, as
an SMTP client is. On the event loop it would stall every request, which is the L05 rule: do not
block the loop. The bookings also run in Starlette's thread pool, and an `asyncio.Queue` is not
thread-safe. So the choice is threads plus `queue.Queue`, with the bound applied before anything is
put on the queue.

## Consequences

- **A booking now answers in milliseconds** (p50 3.4 ms, p95 6.5 ms, 37 ms max under the burst,
  compared with 1.04 s before) and no longer depends on the mail server being up. The booking and the
  confirmation succeed and fail independently, and that independence is what makes the other points
  possible.
- **Uncomfortable: under a burst some guests get a room and no email.** In the measured burst 19 of
  30 guests got no email. The number is counted, visible on GET /stats, and in each answer
  (`notificationFailed: true`), but nothing sends those emails later.
- **Uncomfortable: a killed process loses the queue, and nothing records it.** A polite stop drains
  it (10 of 10) and names whoever is still owed. `kill -9`, a crash or a power cut loses everything
  queued (observed: 10 rows in the database; at the last reading 2 emails were sent, 7 queued and 1 in flight, and the process printed nothing). The bound keeps the
  loss small, at most 10 jobs plus one per worker, but it does not prevent it.
- The counters are the monitoring. `notificationsRejected` above zero in normal running means the
  bound, the worker count or the mail server is wrong, and `notificationsQueued` together with the
  drain time shows which one. Every instance has its own queue and its own counters.
- A retry (when switched on) can produce a second email *at the mail server* if a send timed out
  after the server had in fact accepted it. The queue itself never sends a job twice. This is the
  reason the default is no retry.
- A send in progress cannot be interrupted, because Python cannot stop a thread. Its length is
  bounded by the sender's timeout, and a worker still busy after the join limit is reported, not
  waited for.
- Reservations did not change at all. R6's existing reporting path carries the new refusal.

## When to revisit

- **When a lost confirmation stops being acceptable**, for example when an email carries a payment
  link or a check-in code: move the job into the database in the booking's transaction (the
  transactional outbox, **P17**), so the job and the reservation are saved or lost together.
- **When `notificationsRejected` is regularly above zero** outside real bursts: raise the workers
  first, because that is where the measured throughput came from (0.99 → 1.98 → 3.44 emails per second
  with 1 → 2 → 4 workers). Raise the bound only if longer delays are acceptable.
- **When a second kind of background job appears**, such as SMS or reminders. Two queues with
  hand-written workers is the point where a real job runner (or the outbox worker) costs less than
  maintaining my own.
- **When the app runs as several instances behind a load balancer for real.** Per-instance bounds and
  counters no longer describe the system, and a shared queue is needed.
