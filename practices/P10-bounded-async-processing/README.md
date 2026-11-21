# P10 — Bounded async processing

**Session:** Saturday 14 November 2026, 09:30–10:50 (Asia/Tashkent) · Practice · Group 23-309 SW · Room 232
**Related lecture:** L05 — Application concurrency and database correctness (synchronous vs asynchronous
work, deadlines, cancellation, bounded queues and backpressure, concurrency models)
**Type of work:** evolution of the growing [hotel-booking](../../hotel-booking/README.md) codebase
(version 6 → version 7). The practice measures what the confirmation email costs the booking, takes
it out of the request, shows the unbounded queue filling up, adds a bound and counts what it refuses,
drains the queue on shutdown, chooses a concurrency model, and records the decision as ADR-004.

## Goal

P09 made the booking rule true, but each booking still took a second, because the request waited for
the mail server. In P10 the booking answers as soon as it is committed. The email goes to a **bounded
queue with a fixed number of workers** that **refuses and counts** instead of waiting when it is full.
The **booking result never depends on the email**, and every confirmation ends in a recorded state.
Stopping the app drains the queue within a time limit and **names** whoever is still owed. What the
design still loses (a killed process) is written down, not hidden.

## Outputs (requirement → file)

| Step (activity sheet) | Output | File |
|---|---|---|
| §1 Open your project | P09 checks green first; ADR-003 re-read; `# P10 design notes` | [b0-baseline](evidence/logs/b0-baseline.txt), [design-notes § P10](../../hotel-booking/docs/design-notes.md) |
| 1 · Measure the cost | `send_seconds` (+ timeout, failures) on the email sender; `HOTEL_EMAIL_SECONDS` in the wiring; `tools/burst.py`; the "before" run; queue-trace.md started | [notifications/internal.py](../../hotel-booking/hotel_booking/notifications/internal.py), [main.py](../../hotel-booking/main.py), [tools/burst.py](../../hotel-booking/tools/burst.py), [queue-trace.md](../../hotel-booking/docs/queue-trace.md), [booking-before](diagrams/booking-before.svg) |
| 2 · Hand it to a background worker | `QueuedNotificationSender`; the wiring wraps the email sender; `HeldConfirmations` publishes after COMMIT; booking in milliseconds | the same files, [booking-with-queue](diagrams/booking-with-queue.svg) |
| 3 · Burst it, look at the memory | Unbounded run (`HOTEL_QUEUE_CAPACITY=10000`): 30 / 0 / 29; 30,000 measured | [queue-trace.md § unbounded](../../hotel-booking/docs/queue-trace.md#why-an-unbounded-queue-is-not-the-answer), [unbounded-30000](evidence/logs/unbounded-30000.txt) |
| 4 · Put a bound on it | Capacity (default 10), offer that never waits, counters in the Notifications contract, GET /stats, contract 1.3.0 | [notifications/\_\_init\_\_.py](../../hotel-booking/hotel_booking/notifications/__init__.py), [api.py](../../hotel-booking/hotel_booking/api.py), [openapi.yaml](../../hotel-booking/docs/openapi.yaml) |
| 5 · Backpressure | Bounded run: 11 / 19 / 10, all 30 booked, both readings; the course's three tests | [queue-trace.md § bound](../../hotel-booking/docs/queue-trace.md#with-a-bound-and-counted-rejections), [test_api.py](../../hotel-booking/test_api.py) `QueueTests` |
| 6 · Shutdown | `close(drain, timeout)`; shutdown hook; drain, no drain, SIGTERM, kill -9 observed; "What this design still loses" | [main.py](../../hotel-booking/main.py) `shut_down_notifications`, [shutdown](diagrams/shutdown.svg), [delivery-states](diagrams/delivery-states.svg) |
| 7 · Choose a model | Six lines in design-notes (five rejected + the kept shape + its limit) | [design-notes § P10](../../hotel-booking/docs/design-notes.md), [concurrency-shapes](diagrams/concurrency-shapes.svg) |
| 8 · ADR-004 | Context, decision, rejected shapes, two uncomfortable consequences, when to revisit, all with measured numbers | [adr-004-notification-concurrency.md](../../hotel-booking/docs/adr-004-notification-concurrency.md) |
| §10 Check and hand over | Every check of the sheet's table | [Check your project](#check-your-project-activity-sheet-10) |
| Bounded capacity, explicit full behaviour, fixed workers | Refuse and count (never wait, never drop an older job); a fixed pool of threads | `QueuedNotificationSender`; [test_notification_queue.py](../../hotel-booking/tests/test_notification_queue.py) |
| Timeouts, cancellation, graceful shutdown that drains or reports | Sender timeout; worker poll timeout; drain time limit; a waiting retry is cancelled by shutdown; queued jobs dropped **and named**; a stuck send is reported, not waited for | the same + [test_queue_wiring.py](../../hotel-booking/tests/test_queue_wiring.py) |
| Clear ownership of the concurrency | Only `notifications/internal.py` starts threads (architecture test); the wiring creates the queue and the shutdown hook closes it; 7th border contract keeps Notifications a leaf | [test_architecture.py](../../hotel-booking/tests/test_architecture.py), [.importlinter](../../hotel-booking/.importlinter), [module-dependencies](diagrams/module-dependencies.svg) |
| Booking independent of the email; delivery status recorded | 201 + saved row when the queue is full (`notificationFailed: true`) or the sender fails later; `DeliveryStatus` per reservation, `notificationsFailed`, a log line per refusal, failure and drop | `HeldConfirmations`, `ConfirmationRefused`, `status_of`; tests below |
| Burst tool run for real; queue depth, accepted/rejected, latency with/without, throughput | Every run is a real `python main.py` process (PostgreSQL: the same wiring through `serve_pg.py`) and a real client process | [queue-experiment.txt](evidence/logs/queue-experiment.txt), [queue-results.json](evidence/logs/queue-results.json), [Results](#results) |
| OpenAPI / stats, contract test both ways | 1.3.0; five optional counters; two new examples produced by the real wiring with a real queue | [openapi.yaml](../../hotel-booking/docs/openapi.yaml), [test_openapi_contract.py](../../hotel-booking/tests/test_openapi_contract.py) |
| P09 guarantees still hold | Race tool 0 of 20 (1 and 2 instances, SQLite and PostgreSQL 16); only the winner is emailed | [queue-trace.md § PostgreSQL](../../hotel-booking/docs/queue-trace.md#the-same-on-postgresql-and-p09-still-holds) |
| Diagrams (Mermaid, render-checked) | Before/after sequences, delivery states, shutdown, model choice, class diagram (read by the UML test), as-built modules | [diagrams/](diagrams/), [mmdc log](evidence/logs/mmdc.txt) |
| Evidence, worksheet, reflection | | [evidence/Index.md](evidence/Index.md), [Worksheet.md](Worksheet.md), [reflection](reflections/Jasur-Shermatov.md) |
| Document checks | Sections, numbers = logs, diagrams = code, links, README row | [checks/test_p10_docs.py](checks/test_p10_docs.py) |

## Results

**Observed**: [queue-experiment.txt](evidence/logs/queue-experiment.txt). Linux container, Python 3.13.18,
SQLite 3.53.1, redis-server 7.0.15, PostgreSQL 16.15. Every server is `python main.py` in its own process
on a fresh database. The client is `tools/burst.py` in another process, sending bookings one after
another. The mail server is simulated with `HOTEL_EMAIL_SECONDS`.

| Run | Bookings | Booking latency | Queue: accepted / rejected / queued right after | Afterwards |
|---|---|---|---|---|
| Email inside the request (`--no-queue`), 1 s sender, 1 booking | 1 × 201 | **1.04 s** | — | — |
| the same, 30 bookings | 30 × 201 in **30.2 s** | p50 1004.8 ms, max 1037.1 ms | — | — |
| Queue (10, 1 worker), 1 s sender, 1 booking | 1 × 201 | 35 ms (first request) | 1 / 0 / 0 (1 in flight) | sent 1.0 s later |
| Unbounded (`HOTEL_QUEUE_CAPACITY=10000`), 30 | 30 × 201 in 0.2 s | p50 3.4 ms, max 38.9 ms | **30 / 0 / 29** | Ctrl+C with 3 s limit: 5 sent, 25 dropped and named |
| Unbounded, 30,000 (in-process) | — | — | 30,000 / 0 / 29,999 | 9.8 MB; 8.3 h for one worker |
| **Bounded (10, 1 worker), 30** (+5 reruns) | 30 × 201 in 0.1 s; 30 rows | **p50 3.4 ms, p95 6.5 ms**, max 36.9 ms | **11 / 19 / 10** (every rerun the same) | depth 10 → 0 in 10 s; completed 11 at 11.1 s |
| Bounded, PostgreSQL 16, 30 | 30 × 201; 30 rows (psql) | p50 9.1 ms, p95 31.2 ms | 11 / 19 / 10 | completed 11 at 10.7 s |

| Workers (fixed pool) | 1 s sender, bound 10, burst 30: accepted / drained / emails per s | 0.2 s sender, bound 100, burst 50: drained / emails per s |
|---|---|---|
| 1 | 11 / 10.9 s / 0.99 | 9.9 s / 4.95 |
| 2 | 12 / 5.9 s / 1.98 | 4.8 s / 9.90 |
| 4 | 14 / 3.9 s / 3.44 | 2.5 s / 18.75 |

| Stop (10 accepted, 2 sent, 7 queued, 1 in flight) | What happened |
|---|---|
| Ctrl+C (drain, 30 s limit) | 10 of 10 sent after 7.3 s; "Nobody was owed an email." |
| SIGTERM | the same, 7.2 s |
| `--no-drain` | 3 sent, **7 dropped and named** (R104–R110), 0.2 s |
| `kill -9` | nothing printed; 10 rows in the database; the queued emails gone without a trace |

| Failure runs (all bookings 201) | Result |
|---|---|
| every 3rd attempt fails, no retry (`HOTEL_SEND_ATTEMPTS=1`, the course's policy) | 20 sent, **10 failed**, 10 log lines with ids |
| the same with 3 attempts | 30 sent, 0 failed (9.1 s, backoff 0.5 s → 1 s) |
| 5 s mail server, `HOTEL_EMAIL_TIMEOUT=0.5` | 4 failed after 0.5 s each; the worker moved on |
| P09 race, `HOTEL_SLOW_STEP=1`, 20 rounds: 1 instance / 2 instances / 2 on PostgreSQL | 0 / 0 / 0 double bookings; 20 × (201 + 409) each |

In short, the booking went from **1.04 s to 3.4 ms** (median). Under a burst the queue never held more
than 10 jobs. Every booking succeeded, every refused email was counted and reported in its answer, and
a polite stop owed nobody. The one thing the design still loses is a killed process.

## How to check

```bash
cd hotel-booking
python3 -m unittest -v                 # Ran 19 tests ... OK   (8 booking + 11 API/queue, the course's "19 tests")
python3 -m tests.test_architecture     # Contracts: 7 kept, 0 broken.
python3 -m pytest                      # 540 passed
python3 -m mypy                        # Success: no issues found in 37 source files
HOTEL_EMAIL_SECONDS=1 python3 main.py                     # terminal 1 (Redis running, or add --cache memory)
python3 tools/burst.py --wait                             # terminal 2: 30 x 201; 11 / 19 / 10; caught up after ~11 s
#   then Ctrl+C in terminal 1: "Draining the notification queue ... Nobody was owed an email."
HOTEL_EMAIL_SECONDS=1 python3 main.py --no-queue          # the "before": every booking about 1 s
HOTEL_EMAIL_SECONDS=1 HOTEL_QUEUE_CAPACITY=10000 python3 main.py   # Step 3: the unbounded queue
cd ..
python3 -I practices/P10-bounded-async-processing/evidence/queue_experiment.py hotel-booking   # every run above (~6 min)
python3 practices/P10-bounded-async-processing/evidence/unbounded_30000.py hotel-booking
python3 -m pytest -p no:cacheprovider practices/*/checks                                      # P05-P10 document checks
bash practices/P10-bounded-async-processing/evidence/render_diagrams.sh
```

`render_diagrams.sh` uses `diagrams/puppeteer-config.linux-build.json`. On macOS `mmdc` works without this file: `mmdc -i diagrams/X.mmd -o diagrams/X.svg` (`diagrams/puppeteer-config.linux-build.json` only points the Linux build environment at its headless Chromium).

On the Mac with Docker: `docker compose up -d`, `pip install "psycopg[binary]"`, then
`HOTEL_EMAIL_SECONDS=1 python main.py --db postgres` and the burst. No schema change is needed (P10
changes no table).

## What changed in the code (version 6 → 7)

| File | Change | Kind |
|---|---|---|
| `hotel_booking/notifications/__init__.py` | + `NotificationCounts` (the course's four counters + `failed`, `dropped`, `in_flight`), `DeliveryStatus`, `ConfirmationRefused` | module contract |
| `hotel_booking/notifications/internal.py` | Email sender: `send_seconds`, `timeout_seconds`, `fail_every`, thread-safe count. **New:** `QueuedNotificationSender` (bound, fixed workers, offer that never waits, retry policy, no duplicates, delivery status, `close` with drain/limit/report), `HeldConfirmations` (place inside the transaction, publish after COMMIT, discard on rollback), `ShutdownReport`, `named` | internal |
| `hotel_booking/api.py` | GET /stats + 5 optional counters (`notification_counts`); a shutdown hook (`on_shutdown`, lifespan); `answer(..., omit_unset=True)` | edge |
| `main.py` | `NotificationOptions` + `HOTEL_EMAIL_SECONDS`, `HOTEL_QUEUE_CAPACITY`, `HOTEL_WORKERS`, `HOTEL_SEND_ATTEMPTS`, `HOTEL_EMAIL_TIMEOUT`, `HOTEL_EMAIL_FAIL_EVERY`, `HOTEL_DRAIN_SECONDS` (and flags), `--no-queue`, `--no-drain`; `build_notifications`, `shut_down_notifications`; the unit of work publishes after COMMIT / discards on rollback; version 7 | wiring |
| `hotel_booking/reservations/*`, `rooms/`, `payments/`, `api_stats.py`, `api_cache.py` | **unchanged**: `BookingService` still calls `send_confirmation` once after the save; R6 carries the refusal | — |
| `tools/burst.py` (new) | The burst tool (course output + latency, `--wait`, `--count`, `--year`, `--json`, exit code) | tool |
| `docs/openapi.yaml` | 1.3.0: the email promise; five optional Stats properties; examples `confirmationRefused`, `withQueue`; `notificationFailed` description | contract |
| `.importlinter` | + "Notifications depends on no other module" (7 contracts) | borders |
| `docs/` | `queue-trace.md`, `adr-004-notification-concurrency.md` (new); design-notes § P10; requirements R6 (P10 note) | docs |
| `pyproject.toml`, `requirements.txt`, `README.md` | version 7.0.0 (was 0.10.0; aligned with "version 7" afterwards); mypy files; no new package; README version 7 (limitations updated: two version-6 limitations fixed) | config/docs |

## Deliberate test changes

Old tests after the code change, before any test was touched: **5 failed / 474 passed**, document
checks **1 failed / 184 passed**, and the 16 unittest tests OK
([b1](evidence/logs/b1-old-tests-after-the-code-change.txt)). Each failure was an expected consequence
and was changed on purpose. The reason is written in each module's docstring:

| Test | Now | Why |
|---|---|---|
| `test_openapi_contract.py::test_answer_fields_match_the_pydantic_models` | compares `required` with the fields without a default | The five queue counters are optional (present only with a queue). + two probes (`confirmationRefused`, `withQueue`) through the real wiring and queue |
| `test_uml_conformance.py` (4 failed: classes, namespaces, internal boxes, email sender members) | same names | The diagram moved to the [P10 class diagram](diagrams/class-diagram.mmd): 3 contract and 3 internal classes added, 2 implements lines, 20 → 28 other lines |
| `practices/P08-…/checks::test_as_built_diagram_shows_exactly_the_real_imports` | `LATER_EDGES` = {api → notifications contract} | The P08 picture stays as built in P08. The new edge must exist and is drawn on the [P10 as-built diagram](diagrams/module-dependencies.mmd), checked exactly by the P10 checks |
| `practices/P09-…/checks::test_the_contract_adds_the_race_example_and_is_1_2_0` | asks for 1.2 or later | Contract 1.3.0; the race example is still required |
| `test_architecture.py` (not failing, extended) | 7 contracts; self-test "rule3" now expects two broken contracts; + "queue-reaches-rooms" case; + "only the queue starts threads" and its red case | The new border and the ownership rule |
| `test_api.py` (not failing, extended) | + the course's three queue tests (`QueueTests`) | Step 5.1; 16 → 19 unittest tests |

New tests: [tests/test_notification_queue.py](../../hotel-booking/tests/test_notification_queue.py) (26),
[tests/test_queue_wiring.py](../../hotel-booking/tests/test_queue_wiring.py) (15),
[tests/test_burst.py](../../hotel-booking/tests/test_burst.py) (6), the course's 3 in `test_api.py`, plus
the architecture, contract and UML additions. The P09 race tests did not change and still pass.

### The tests for each required behaviour

| Behaviour | Tests |
|---|---|
| Queue full: refused, counted, never waits, booking still 201 | `test_a_full_queue_refuses_counts_and_never_waits` (exact 11/19 with a held worker), `test_handing_over_never_waits_even_for_a_one_second_sender`, `test_the_bound_holds_and_the_sums_balance_under_many_producers` (8 producers, 3 workers, 200 readings), `test_a_full_queue_never_fails_a_booking`, `QueueTests.test_a_burst_larger_than_the_bound_is_refused_and_counted` |
| Worker failure and the retry policy | `test_without_retry_a_failed_send_is_counted_logged_and_the_worker_goes_on`, `test_a_failing_job_does_not_stop_the_worker`, `test_retry_sends_once_after_two_failures`, `test_retry_gives_up_after_the_last_attempt_and_waits_longer_each_time`, `test_a_retry_never_takes_another_guests_place`, `test_a_failing_mail_server_never_fails_a_booking` |
| Timeouts | `test_the_senders_own_timeout_bounds_a_hanging_mail_server`, `test_a_drain_has_a_time_limit`, `test_a_send_that_will_not_end_is_reported_not_waited_for` |
| Shutdown and drain | `test_close_with_drain_finishes_everything_and_reports_nobody_owed`, `QueueTests.test_a_drained_shutdown_finishes_everything_it_accepted`, `test_closing_refuses_new_work_at_once`, `test_close_is_idempotent_and_the_context_manager_drains`, `test_closing_stops_every_worker_thread`, `test_stopping_the_server_runs_the_drain`, `test_the_real_server_drains_its_queue_when_it_is_stopped[ctrl-c / sigterm]` |
| Cancellation | `test_close_without_drain_cancels_the_queue_and_names_every_guest_owed`, `test_shutdown_cancels_a_waiting_retry_at_once`, `test_shutdown_without_the_drain_names_who_is_owed` |
| No duplicate sends | `test_the_same_confirmation_offered_twice_is_sent_once`, `test_many_workers_and_retries_still_send_every_email_exactly_once` (300 jobs, 4 workers), the duplicate check inside the many-producers test |
| After COMMIT only; rollback never emailed | `test_the_worker_only_ever_sees_committed_bookings`, `test_a_booking_that_rolls_back_is_never_emailed`, `test_held_confirmations_reach_the_workers_only_after_publish`, `test_a_held_place_counts_against_the_bound_and_a_discard_gives_it_back` |
| Delivery status recorded | `test_delivery_status_follows_a_job_and_the_history_is_bounded`, `test_a_shutdown_log_line_names_at_most_a_hundred_guests` |
| P09 guarantees still hold | `test_the_race_still_gives_the_room_to_one_guest_and_one_email`, all of `tests/test_concurrency.py`, the two P09 tests in `test_api.py`; E15–E16 |

## Substitutions (honest record)

| Course material uses | This portfolio uses | Why | Requirement still covered by |
|---|---|---|---|
| FastAPI + SQLAlchemy + psycopg (`python main.py` on PostgreSQL 18 in Docker) | Starlette + pydantic + sqlite3 (P07 decision); PostgreSQL runs through `serve_pg.py`, which uses the same wiring with P09's `pg_wire` | No PyPI, no Docker daemon | E7 on SQLite through `python main.py`; E16 on PostgreSQL 16.15; Docker + psycopg: **to do by the student** (E22) |
| `$env:HOTEL_EMAIL_SECONDS = "1"; python main.py` (PowerShell) | `HOTEL_EMAIL_SECONDS=1 python3 main.py` | I use macOS | — |
| Two terminals typed by hand | `queue_experiment.py` starts `python main.py` and runs `tools/burst.py` / `race_http.py` as separate processes and sends the real signals | Repeatable, and every output is kept | [queue-experiment.txt](evidence/logs/queue-experiment.txt) |
| Step 1 measured before the queue exists | `--no-queue` keeps the P09 behaviour in the same code | The code change was made in one piece. The flag makes "before" a real run | E3 |
| `close()` after `uvicorn.run` in a `finally` | The app's shutdown hook (lifespan), plus a `finally` as a safety net | uvicorn re-raises SIGTERM after its shutdown, so the `finally` never runs for SIGTERM (found with a real-process test) | E12, `test_the_real_server_drains_its_queue_when_it_is_stopped[sigterm]` |
| Without a drain the jobs stay on the queue (`queued=6`) until the process exits | They are dropped and named (`dropped=7`, ids logged) | A loss you can read in the log is better than one that only disappears | E11 |
| Four counters; a failed send leaves `accepted ≠ completed + queued` | + `notificationsFailed` (and `dropped` in the report) | A failure is then never mistaken for a silent loss | Contract 1.3.0; tests above |
| `put_nowait` on a `Queue(maxsize)` | A `BoundedSemaphore` place (taken inside the transaction) + `put_nowait` on a `Queue(maxsize)` | Publishing after COMMIT needs the place reserved first, so the refusal can still reach the answer | `test_a_held_place_counts_against_the_bound_…` |
| Contract version 1.2.0 | 1.3.0 | P09 already used 1.2.0 | P10 check |
| "22 green: 19 tests + 3 contracts" | 19 unittest tests and **7** contracts; full suite 540 | The portfolio adds tests and borders beyond the course's | E17 |
| `lint-imports` | the stdlib ast border test | import-linter cannot be installed here | `python -m tests.test_architecture` |

## What was and was not observed

- **Observed through `python main.py` (SQLite, real Redis):** the before/after latency, the unbounded
  and bounded bursts with the queue depth, the worker counts, the failure, retry and timeout runs,
  Ctrl+C, SIGTERM, `--no-drain` and `kill -9`, and the P09 race with one and two instances.
- **Observed on PostgreSQL 16.15** (same wiring, `pg_wire` driver): the bounded burst, the drain, and
  the race across two instances, counted with psql.
- **Observed in-process:** the 30,000-job unbounded queue (memory and time).
- **Not observed here (to do by the student on the Mac):** Docker (PostgreSQL 18, Redis 8),
  `python main.py --db postgres` with psycopg, `lint-imports`, the commit, and the pair work.

## Check your project (activity sheet §10)

| Check (activity sheet) | What you should see | Seen here | Status |
|---|---|---|---|
| Your checks | 22 green (Python: 19 tests, then 3 contracts) | `Ran 19 tests … OK`; `Contracts: 7 kept, 0 broken.`; pytest 540 passed ([f-unittest](evidence/logs/f-unittest.txt), [f-contracts](evidence/logs/f-contracts.txt), [f-pytest](evidence/logs/f-pytest.txt)) | ✓ Observed |
| A booking with `HOTEL_EMAIL_SECONDS=1` | 201 Created in milliseconds, not a second | 35 ms for the first request; p50 3.4 ms in bursts (was 1.04 s) | ✓ Observed |
| The burst tool | all 30 accepted; some confirmations refused and counted | 30 × 201; 19 refused, counted, and `notificationFailed: true` in 19 answers | ✓ Observed |
| GET /stats | four notification counters next to the cache counters | five (the four + `notificationsFailed`) | ✓ Observed |
| accepted + rejected | exactly 30 after a burst of 30 | 11 + 19 = 30 (6 of 6 runs) | ✓ Observed |
| queued | never above your capacity | max 10 (bound 10), every reading | ✓ Observed |
| After the worker catches up | accepted = completed, queued = 0 | 11 = 11, 0, after 11.1 s | ✓ Observed |
| Ctrl+C | drains the queue and says so | "Draining the notification queue: 8 to go … Nobody was owed an email." (also SIGTERM) | ✓ Observed |
| docs/queue-trace.md | before, unbounded, bounded, shutdown, and what it still loses | [queue-trace.md](../../hotel-booking/docs/queue-trace.md) | ✓ |
| docs/adr-004-notification-concurrency.md | the model, five rejected, consequences, when to revisit | [ADR-004](../../hotel-booking/docs/adr-004-notification-concurrency.md) | ✓ |

## Requirements checklist

Sources: the P10 Activity sheet (the same as the Student explanation, Student notes and Presentation
notes apart from the title block, compared with `diff`), the catalog entry (Sat 14 Nov 2026, room 232),
L05 (async work, deadlines, cancellation, bounded queues, backpressure, concurrency models), the Python
reference (interfaces: `QueuedNotificationSender`, `NotificationCounts`, `close(drain)`, `tools/burst.py`,
the three tests, the HOTEL_* variables) and my own portfolio conventions.

| # | Requirement (source) | Where it is satisfied | Status |
|---|---|---|---|
| 1 | §1: Docker running, `docker compose up -d` | — | **To do by the student** (no daemon here; local redis-server and PostgreSQL 16 used instead) |
| 2 | §1: P09 checks green; re-read ADR-003 Consequences; `# P10 design notes` heading | E1; Worksheet §1; design-notes § P10 | Done — Observed |
| 3 | Step 1: `send_seconds` on the email sender, default 0 | `EmailNotificationSender` | Done — Observed |
| 4 | Step 1: `HOTEL_EMAIL_SECONDS` read in the wiring | main.py; `test_the_queue_settings_come_from_the_environment_and_the_flags` | Done — Observed |
| 5 | Step 1: the burst tool | tools/burst.py; tests/test_burst.py | Done — Observed |
| 6 | Step 1: run with a slow sender; queue-trace.md "What the email was costing the guest" | E3; queue-trace.md | Done — Observed |
| 7 | Step 2: the queued sender next to the email sender; the wiring wraps it; checks green | internal.py, main.py; E17 | Done — Observed |
| 8 | Step 2: one booking answers in milliseconds; "With a queue in front of the sender" | E4; queue-trace.md | Done — Observed |
| 9 | Step 3: unbounded burst, three numbers, the 30,000 line | E5, E6; queue-trace.md | Done — Observed |
| 10 | Step 4: capacity from `HOTEL_QUEUE_CAPACITY` (default 10); offer that never waits | `reserve`/`offer`; `test_handing_over_never_waits…` | Done — Observed |
| 11 | Step 4: four counters, published by the Notifications contract; GET /stats with a queue | `NotificationCounts`; api.py; `test_stats_show_the_queue_only_when_there_is_one` | Done — Observed |
| 12 | Step 4: Stats schema in openapi.yaml, version raised | 1.3.0 (1.2.0 was used by P09); contract test both ways | Done — Observed |
| 13 | Step 5: burst against the bound; accepted + rejected = 30; queued ≤ 10; caught up after ~11 s | E7 | Done — Observed |
| 14 | Step 5: the three tests; 22 green | `QueueTests`; 19 unittest OK + 7 contracts | Done — Observed |
| 15 | Step 5: "With a bound, and counted rejections" with both readings; the line about rejected > 0 | queue-trace.md | Done |
| 16 | Step 6: close with a drain, called when the app stops | `close`, `shut_down_notifications`, lifespan hook; E10, E12 | Done — Observed |
| 17 | Step 6: Ctrl+C after a burst, final counters | E10 | Done — Observed |
| 18 | Step 6: "What stopping the app does" and "What this design still loses" (outbox) | queue-trace.md; E11, E13 | Done — Observed |
| 19 | Step 7: six lines (five rejections about the work, the kept shape, its limit) | design-notes § P10; Worksheet §8 | Done |
| 20 | Step 8: ADR-004 with the five headings, five rejections, two uncomfortable consequences, ≥ 2 revisit conditions | adr-004; `test_adr_004_*` | Done |
| 21 | §10: run every check; re-read the ADR | [Check your project](#check-your-project-activity-sheet-10); E17 | Done — Observed |
| 22 | §10: commit "P10: send confirmations from a bounded queue"; bring the folder to P11; pair work, swap the typist | — | **To do by the student** (no git in this build) |
| 23 | Bounded capacity, explicit full behaviour (refuse), fixed number of workers | `QueuedNotificationSender`; E7, E9 | Done — Observed |
| 24 | Timeouts | sender timeout (E14), worker poll timeout, drain time limit (E5), join limit; tests | Done — Observed |
| 25 | Cancellation | `--no-drain` / drain limit cancel queued jobs (E5, E11); a waiting retry is cancelled; tests | Done — Observed |
| 26 | Graceful shutdown that drains or reports pending work | E10–E12; the names of whoever is owed | Done — Observed |
| 27 | Clear ownership of the concurrency | only the queue starts threads (ast test); wiring creates, hook closes; 7th contract | Done — Observed |
| 28 | Booking independent of the email; delivery status recorded | 201 + row when full / failing (E7, E14); `DeliveryStatus`, counters, logs; after-COMMIT publish | Done — Observed |
| 29 | Burst tool run for real; queue depth, accepted/rejected, latency with/without, worker throughput | E3–E9, E16; [Results](#results) | Done — Observed |
| 30 | docs/queue-trace.md (a traced run step by step) | queue-trace.md (outputs copied from the log, checked line by line) | Done — Observed |
| 31 | ADR-004 in own words with real numbers | adr-004 (numbers checked against the logs) | Done |
| 32 | OpenAPI/stats updates; contract test passing both ways | openapi 1.3.0; E19 | Done — Observed |
| 33 | module-boundary rules kept; .importlinter + ast test updated | 7 contracts kept; ownership rule; E17 | Done — Observed |
| 34 | Tests for queue full, failure/retry, shutdown/drain, cancellation, no duplicate sends, P09 guarantees | [The tests for each required behaviour](#the-tests-for-each-required-behaviour) | Done — Observed |
| 35 | Earlier tests green; changes deliberate, with notes | [Deliberate test changes](#deliberate-test-changes); E2, E17 | Done — Observed |
| 36 | README, worksheet, diagrams (mmdc render-checked), evidence, reflection; root README row | this file, Worksheet.md, diagrams/ + E20, evidence/, reflections/, root README | Done |
| 37 | Stop everything started | the scripts stop every server, redis-server and the PostgreSQL cluster in `finally` blocks; E21 | Done — Observed |

## Self-check before submission

- [x] The booking answers in milliseconds with a one-second mail server (logged, not described)
- [x] A full queue refuses and counts; it never waits, and the booking still succeeds (30 of 30)
- [x] The email is published only after the COMMIT; a rollback is never emailed
- [x] Ctrl+C and SIGTERM drain; `--no-drain` names who is owed; `kill -9` is written down as a loss
- [x] Every number in queue-trace.md, ADR-004 and this README comes from a log (the document checks compare them)
- [x] Nothing claims a Docker, psycopg, `lint-imports` or git run that did not happen
