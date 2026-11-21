# P10 Worksheet — answers to every "Your turn"

Student: Jasur Shermatov · Group 23-309 SW · Session: Saturday 14 November 2026, 09:30–10:50, room 232.
Evidence labels as agreed in L01: **Observed** (run, output in [evidence/logs](evidence/logs/)),
**Simulated**, **Proposed**. The course uses Docker, PostgreSQL 18 and PowerShell
(`$env:HOTEL_EMAIL_SECONDS = "1"`). This build ran `HOTEL_EMAIL_SECONDS=1 python3 main.py` (macOS/Linux
syntax) on SQLite with a local redis-server, and repeated the main runs on a local PostgreSQL 16. The
substitutions are listed in the [README](README.md#substitutions-honest-record).

## §1 · Open your project

1. *Docker Desktop.* **To do by the student** on the Mac. The build container has the Docker CLI but
   no daemon ([f-tools](evidence/logs/f-tools.txt)).
2. *Open the folder and two terminals.* Done. In the evidence, terminal 1 is a `python main.py`
   process and terminal 2 is `tools/burst.py` / `tools/race_http.py`, both started by
   [queue_experiment.py](evidence/queue_experiment.py).
3. *P09 checks green.* **Observed** ([b0-baseline](evidence/logs/b0-baseline.txt)): 16 unittest tests OK and
   "Contracts: 6 kept" (the course's "19 green" is 16 + 3; my portfolio has 6 contracts). The full
   suite: 479 passed, mypy clean.
4. *Read ADR-003's Consequences.* Re-read. The one that matters today is "the rule is in the
   database, every writer passes it". Nothing in P10 may move the rule, which is also why the actor
   alternative is rejected in ADR-004.
5. *`# P10 design notes`.* Added to [design-notes.md](../../hotel-booking/docs/design-notes.md#p10-design-notes).

## §2 · Step 1 — Measure the cost

1. *`sendSeconds` on the email sender (1.1), default 0.* `EmailNotificationSender(send_seconds=0.0,
   timeout_seconds=None, fail_every=0)` in [notifications/internal.py](../../hotel-booking/hotel_booking/notifications/internal.py).
   Besides the delay, it can time out as an SMTP client would, and it can fail every n-th attempt
   (a flaky mail server, used for the retry policy).
2. *`HOTEL_EMAIL_SECONDS` in the wiring.* [main.py](../../hotel-booking/main.py): `NotificationOptions` and
   `--email-seconds`, together with the other P10 variables
   (`test_the_queue_settings_come_from_the_environment_and_the_flags`).
3. *Checks still green.* Yes. The delay is 0 unless it is asked for.
4. *The burst tool (1.2).* [tools/burst.py](../../hotel-booking/tools/burst.py) is my own stdlib version.
   It prints the course's lines plus the latency distribution and the `notificationFailed` count,
   and adds `--wait` (drain time and throughput), `--count`, `--year`, `--json` and an exit code.
   Tests: [tests/test_burst.py](../../hotel-booking/tests/test_burst.py).
5. *Run it with `HOTEL_EMAIL_SECONDS=1`.* **Observed**. I wrote the queue in the same piece of work as
   Step 1, so the "before" run uses `python main.py --no-queue`, which is the P09 behaviour kept for
   exactly this comparison: 1 booking 1.04 s, 30 bookings 30.2 s.
6. *docs/queue-trace.md.* Created with the course's heading, and my own output is under
   "What the email was costing the guest" ([queue-trace.md](../../hotel-booking/docs/queue-trace.md)).

## §3 · Step 2 — Take the email out of the request

1. *The queued sender next to the email sender (2.1).* `QueuedNotificationSender` in the same
   `internal.py`.
2. *Wrap it in the wiring (2.2).* `build_notifications` creates the one queue of the process. Each
   request's unit of work gives `BookingService` a `HeldConfirmations` over it, which holds a place
   during the transaction and publishes after the COMMIT. My addition beyond the course: version 6
   sent the email *before* the commit (a known limitation in its README).
3. *JavaScript/Dart only.* Not applicable to Python.
4. *Checks still green.* Yes, all 16 unittest tests. The P07 test that keeps the email inside
   the transaction (`SlowSender`) still uses a plain sender on purpose.
5. *One booking with curl.* **Observed** with `burst.py --count 1`: 201 in 35 ms (the first request of a
   fresh process). Inside a burst the same booking is p50 3.4 ms. The email followed 1.0 s later.
6. *"With a queue in front of the sender".* Written, with that output.

## §4 · Step 3 — Watch it fill

1–2. `HOTEL_EMAIL_SECONDS=1 HOTEL_QUEUE_CAPACITY=10000 python main.py`, then the burst. **Observed**.
3. *The three numbers.* **accepted 30, rejected 0, queued 29** (the 30th was in flight).
4. *"Why an unbounded queue is not the answer".* Written with my own output, plus what the drain
   limit did at Ctrl+C (25 guests dropped and named).
5. *One line: thirty thousand?* Measured in-process ([unbounded-30000](evidence/logs/unbounded-30000.txt)):
   all 30,000 accepted in 1.26 s, 9.8 MB held, and 8.3 hours of sending for one worker. Nothing
   refuses them. With a large or endless burst, memory grows until the process dies and takes the
   bookings with it.

## §5 · Step 4 — Bound it

1. *Capacity from `HOTEL_QUEUE_CAPACITY`, default 10.* Yes (`NotificationOptions.capacity`).
2. *Offer, never wait (4.1).* `reserve()` takes a place with `BoundedSemaphore.acquire(blocking=False)`
   and the job goes in with `put_nowait`. `send_confirmation` never waits and never raises. A full
   queue is counted as rejected (`test_handing_over_never_waits_even_for_a_one_second_sender`:
   30 hand-overs in under 0.1 s with a 1 s sender).
3. *Four counters (4.2) from the Notifications contract (4.3).* `NotificationCounts(accepted,
   rejected, completed, queued, failed, dropped)` with `in_flight` in
   [notifications/__init__.py](../../hotel-booking/hotel_booking/notifications/__init__.py). The course's
   four plus `failed` and `dropped`, so that a failure or a shutdown drop is never confused with a
   silent loss.
4. *The Stats schema and the version.* [openapi.yaml](../../hotel-booking/docs/openapi.yaml): five optional
   properties. The version is **1.3.0**, not the sheet's 1.2.0, because P09 already used 1.2.0.
5. *GET /stats includes them when wired with a queue.* Yes (`notification_counts` in `create_app`),
   and leaves them out without a queue (`test_stats_show_the_queue_only_when_there_is_one`).
6. *Checks still green.* Yes.

## §6 · Step 5 — Make it refuse

1. *Burst against the default bound.* **Observed**: Accepted 30, Rejected 0 (bookings), and on the
   queue **11 accepted / 19 rejected / 10 queued**. 19 answers said `notificationFailed: true`, and
   30 rows are in the database.
2. *accepted + rejected = 30, queued ≤ 10.* 11 + 19 = 30, and queued 10. Five more runs gave the same.
3. *About eleven seconds later.* `GET /stats, 11.1 seconds later`: accepted 11 = completed 11, queued 0.
   The queue depth every half second is in the trace (10 → 0 in 10 s).
4. *The three tests (5.1), 22 green.* Added to [test_api.py](../../hotel-booking/test_api.py) (`QueueTests`):
   `python -m unittest` ran **19 tests OK** and there are 7 contracts kept (the course's 19 + 3;
   mine 19 + 7). Another 47 P10 tests are in `tests/`.
5. *"With a bound, and counted rejections".* Written, with both readings.
6. *One line: rejected above zero in normal running?* It means the mail server, the worker count or
   the bound is wrong for the traffic. `queued` and the drain time show which one. Rejections are
   acceptable only during a real burst.

## §7 · Step 6 — Drain it

1. *close with a drain (6.1).* `close(drain=True, timeout=None) -> ShutdownReport`. It stops accepting
   first, waits until nothing is queued or in flight or the time limit is reached, stops the workers
   (a waiting retry is cancelled), then drops and names whatever is left. It is idempotent and also a
   context manager.
2. *Call it when the app stops.* `shut_down_notifications`, run by the app's shutdown hook (lifespan),
   after uvicorn has finished the open requests. I first had it after `uvicorn.run`. A test with a
   real process showed that uvicorn re-raises SIGTERM after its shutdown, so that code never ran for
   SIGTERM.
3. *Ctrl+C after the burst.* **Observed**: "Stopping the app with 10 confirmations accepted and 2 sent
   so far... Draining the notification queue: 8 to go (at most 30 s) ... completed=10 ... Nobody was
   owed an email." The same for SIGTERM.
4. *Final counters.* accepted 10 = completed 10, queued 0.
5. *"What stopping the app does".* Written with four real runs: drain, `--no-drain` (7 dropped and
   named), SIGTERM, and kill -9 (nothing printed, 10 rows, the queue lost).
6. *"What this design still loses".* Written: an in-memory queue does not survive a killed process,
   the reservation survives and the job does not, and the fix is the transactional outbox (P17).

## §8 · Step 7 — Pick one and say why

1–4. Six lines in [design-notes.md](../../hotel-booking/docs/design-notes.md#six-shapes-one-line-each-step-7).
Each reason describes the work, not a library:

- Structured concurrency: the request does not own this work, and the email must outlive the request.
- Fork-join: the email is not a part of the booking, and nobody waits for it.
- Reactive pipeline: there is only one stage.
- Actor per room: there is no per-room state in sending an email, and it would move the rule out of the database.
- STM: there is no shared mutable state to compose.
- **Kept:** a bounded queue with fixed workers, because the work is one stage, nobody waits for it, and
  the consumer can be slower than the producer, so it needs a limit I choose.
- **Cannot do:** survive the process being killed.

The decision path is drawn in [concurrency-shapes](diagrams/concurrency-shapes.svg).

## §9 · Step 8 — Record the decision

1–5. [adr-004-notification-concurrency.md](../../hotel-booking/docs/adr-004-notification-concurrency.md) has the
five headings, seven rejected options (the course's five, "no queue" and "unbounded", plus asyncio tasks
as an implementation alternative), the two uncomfortable consequences written out ("under a burst some
guests get a room and no email"; "a killed process loses the queue, and nothing records it"), and four
revisit conditions. Every number in it comes from the logs (checked by
[test_p10_docs.py](checks/test_p10_docs.py)).

## §10 · Hand it over

1. *Run every check.* Done ([Check your project](README.md#check-your-project-activity-sheet-10)).
2. *Commit "P10: send confirmations from a bounded queue".* **To do by the student** (no git in this build).
3. *Re-read the ADR.* Done. A stranger can see why each shape was rejected, because each reason is a
   property of the work.
4. *Bring the folder to P11.* **To do by the student.** The folder is ready.
