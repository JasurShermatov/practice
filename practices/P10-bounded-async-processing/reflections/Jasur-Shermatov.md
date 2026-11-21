# Reflection — P10 Bounded async processing

Jasur Shermatov · 23-309 SW · Session: Saturday 14 November 2026, 09:30–10:50, room 232

## What I expected

I thought "make the email asynchronous" would be a one-line change: put the call in a background
thread and be done. The measurement before the change agreed with that picture. With a one-second
mail server every booking took about a second, and thirty of them took about thirty seconds, while
the booking itself took a few milliseconds (numbers in
[queue-trace.md](../../../hotel-booking/docs/queue-trace.md)).

## What surprised me

- **The unbounded queue looked like a success.** All thirty guests were answered in milliseconds.
  Only one number, the queue depth on GET /stats, showed that the work had not gone away; it was
  sitting in memory. If I had not published the counters I would have called the unbounded version
  finished.
- **The invariant still balanced when work was about to be lost.** Without a drain, the counters
  said `accepted = completed + queued` right up to the moment the process exited, and then the
  queued jobs vanished with no trace. That is why my shutdown does not leave them on the queue. It
  drops them explicitly and names each reservation id in the log. This does nothing for `kill -9`,
  and I wrote that down instead of hiding it.
- **Two bugs that the course reference does not show.** In version 6 the confirmation was sent
  *before* the COMMIT. With a queue that gets worse, because a worker could email a guest about a
  booking whose transaction later rolls back. Holding a place inside the transaction and publishing
  it only after the commit fixed that. It also let me tell the guest in the 201 answer when the queue
  had no room (`notificationFailed: true`). Both cases are covered by tests that fail when the order
  is wrong.
- **SIGTERM is not Ctrl+C.** uvicorn re-raises the signal after its own shutdown, so a `finally`
  after `uvicorn.run` never runs for SIGTERM. The drain had to move into the app's shutdown hook. I
  only found this by stopping a real process with both signals in a test.

## What I would do differently

I would measure the "before" state *before* writing the queue, as the sheet orders it. I wrote the
queue first and had to add `--no-queue` so that the "before" numbers came from the same code. That
flag turned out to be useful for the comparison anyway, but the order was backwards.

## The decision in one sentence

One stage, nobody waiting, and a consumer slower than the producer: a bounded queue with a fixed
number of workers that refuses and counts when full is the smallest design with a limit I chose
myself. The cost I accept is that, until the outbox in P17, an in-memory queue loses its jobs when
the process is killed.

## To do by me (not possible in the build environment)

- Run the checks and the burst on my Mac with Docker (PostgreSQL 18, Redis 8) and
  `python main.py --db postgres` with psycopg.
- Do the pair work and swap the typist at each step, then commit with
  "P10: send confirmations from a bounded queue".
