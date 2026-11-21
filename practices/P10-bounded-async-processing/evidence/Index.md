# Evidence index — P10

Labels as agreed in L01/P01: **Proposed** (planned, not run), **Simulated** (model or thought
experiment), **Observed** (actually run, with the command, environment and real output recorded).
Environment for every Observed row: Linux container (2 vCPU), Python 3.13.18, pytest 9.1.1, mypy
2.3.1 (strict), Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1, redis-server 7.0.15,
**PostgreSQL 16.15** (a throw-away cluster on 127.0.0.1, created and deleted by the script), and Mermaid
CLI 11.16.0 with headless Chromium. There is no Docker daemon, no psycopg and no import-linter
([f-tools](logs/f-tools.txt)). Portfolio build of 2026-11-21.

Scripts: [queue_experiment.py](queue_experiment.py) (every server is `python main.py` in its own
process; [serve_pg.py](serve_pg.py) for PostgreSQL, through P09's `pg_wire`),
[unbounded_30000.py](unbounded_30000.py), [render_diagrams.sh](render_diagrams.sh). Main outputs:
[queue-experiment.txt](logs/queue-experiment.txt) and [queue-results.json](logs/queue-results.json).

| ID | Label | Requirement | Action | Expected | Actual | Limitation |
|---|---|---|---|---|---|---|
| E1 | **Observed** | §1: P09 checks green before any change | unittest, contracts, pytest, mypy on version 6 | 16 OK, 6 kept, 479 passed | as expected ([b0-baseline](logs/b0-baseline.txt)) | — |
| E2 | **Observed** | Old tests after the code change, before touching any | full pytest + document checks on the P10 code | some red, each explained | 5 failed / 474 passed, document checks 1 failed / 184 passed, unittest 16 OK ([b1](logs/b1-old-tests-after-the-code-change.txt)); every one changed deliberately (README) | — |
| E3 | **Observed** | Step 1: what the email costs inside the request | `HOTEL_EMAIL_SECONDS=1 python main.py --no-queue`; `burst.py --count 1`, then 30 | about 1 s per booking, about 30 s for 30 | 1.04 s; 30 in 30.2 s, p50 1004.8 ms ([queue-experiment](logs/queue-experiment.txt) Step 1) | Simulated mail server (a delay), not SMTP |
| E4 | **Observed** | Step 2: the same booking with the queue | `HOTEL_EMAIL_SECONDS=1 python main.py`; `burst.py --count 1 --wait` | 201 in milliseconds; the email follows | 35 ms (first request of the process); completed 1 after 1.0 s | — |
| E5 | **Observed** | Step 3: the unbounded queue | `HOTEL_QUEUE_CAPACITY=10000`; burst of 30 | accepted 30, rejected 0, about 29 queued | 30 / 0 / 29; Ctrl+C with a 3 s limit: 5 sent, 25 dropped and named; 30 rows | — |
| E6 | **Observed** | Step 3: "what would 30,000 do?" | `unbounded_30000.py` (in-process, one held worker) | all accepted, memory grows | 30,000 accepted in 1.26 s, 9.8 MB, 8.3 h for one worker ([unbounded-30000](logs/unbounded-30000.txt)) | In-process, not over HTTP |
| E7 | **Observed** | Steps 4–5: the bound refuses and counts; queue depth | default bound 10, 1 worker; burst of 30; GET /stats every 0.5 s | accepted + rejected = 30, queued ≤ 10, all 201 | 11 / 19 / 10; 19 answers `notificationFailed: true`; 30 rows; depth 10 → 0 in 10 s; completed 11 at 11.1 s; 5 more runs: 11/19/10 every time | — |
| E8 | **Observed** | Booking latency with and without the queue | the same bursts | the queue removes the email from the latency | without: p50 1004.8 ms, max 1037.1 ms. With: p50 3.4 ms, p95 6.5 ms, max 36.9 ms (5 reruns: p50 3.4–4.4, p95 5.6–22.9 ms) | One client, sequential (as the course) |
| E9 | **Observed** | Worker throughput (fixed pool) | `HOTEL_WORKERS` 1, 2, 4 × (1 s sender, bound 10, burst 30) and (0.2 s, bound 100, burst 50); `burst.py --wait` | throughput grows with the workers; the bound decides acceptance | 0.99 / 1.98 / 3.44 and 4.95 / 9.90 / 18.75 emails per second; accepted 11 / 12 / 14 | — |
| E10 | **Observed** | Step 6: Ctrl+C with the drain | 10 bookings, stop after about 2.6 s | drains, nobody owed | "8 to go", 10 of 10 sent, stopped after 7.3 s, "Nobody was owed an email." | — |
| E11 | **Observed** | Step 6: without the drain | `--no-drain` | the rest is lost | completed 3, dropped 7, each named (R104–R110) | Mine drops and names them; the course's version leaves them queued |
| E12 | **Observed** | Shutdown by SIGTERM (deploys) | the same, `kill -TERM` | the same drain | 10 of 10, 7.2 s, nobody owed | — |
| E13 | **Observed** | What a killed process loses | the same, `kill -9` | nothing printed, jobs lost | no output at all; 10 rows in the database; 2 sent, 7 queued and 1 in flight at the last reading | — |
| E14 | **Observed** | Failures: no retry vs retry; the sender's timeout | `HOTEL_EMAIL_FAIL_EVERY=3` with `HOTEL_SEND_ATTEMPTS` 1 and 3; `HOTEL_EMAIL_SECONDS=5 HOTEL_EMAIL_TIMEOUT=0.5` | failures counted and logged; retry recovers; timeout frees the worker | 20 sent / 10 failed (10 log lines with ids) → 30 sent / 0 failed; 4 failed after 0.5 s each; every booking 201 | Flakiness is simulated (every 3rd attempt) |
| E15 | **Observed** | P09 still holds with the queue | `HOTEL_SLOW_STEP=1 HOTEL_EMAIL_SECONDS=1`; `race_http.py --repeat 20`, 1 and 2 instances (SQLite) | 0 double bookings | 0 of 20 rounds, 20 × (201 + 409), in both | — |
| E16 | **Observed** | The same on PostgreSQL 16 | `serve_pg.py` (same wiring, `pg_wire`); bounded burst; race to 2 instances | same split; no double booking | 11 / 19 / 10, p50 9.1 ms; 30 rows (psql); completed 11 after 10.7 s; race 0 of 20; psql: no pair | Driver = `pg_wire`, not psycopg; PostgreSQL 16, not 18 |
| E17 | **Observed** | Everything at the end | unittest, contracts, pytest, mypy, demo, race, document checks | all green | 19 OK; 7 kept; 540 passed (50 new P10 tests); mypy clean; demo and race output unchanged ([f-unittest](logs/f-unittest.txt), [f-contracts](logs/f-contracts.txt), [f-pytest](logs/f-pytest.txt), [f-mypy](logs/f-mypy.txt), [f-demo](logs/f-demo.txt), [f-doc-checks](logs/f-doc-checks.txt)) | — |
| E18 | **Observed** | The timing-based tests are stable | queue + wiring + course queue tests, 20 times | green every time | 20 × "42 passed" ([f-stability](logs/f-stability.txt)) | 2-vCPU container |
| E19 | **Observed** | Contract equal to the code both ways, 1.3.0; the new examples produced by the real wiring with a real queue | `tests/test_openapi_contract.py` | green | green (inside E17); `withQueue` and `confirmationRefused` are probe answers | Swagger editor not opened |
| E20 | **Observed** | Diagrams render | `render_diagrams.sh` | 7 × exit 0 | 7 × exit 0 ([mmdc](logs/mmdc.txt)) | — |
| E21 | **Observed** | Nothing left running | `pgrep` for main.py, uvicorn, redis-server and postgres after the runs | none | none ([f-cleanup](logs/f-cleanup.txt)) | — |
| E22 | **Proposed** | On the Mac with Docker (PostgreSQL 18, Redis 8) and psycopg | `docker compose up -d`; `HOTEL_EMAIL_SECONDS=1 python main.py --db postgres`; `python tools/burst.py --wait`; Ctrl+C | 201 in ms; 11/19 (or 10/20); drain prints "Nobody was owed an email." | Not run here: **to do by the student** | — |
| E23 | **Simulated** | Is a bound of 10 with 1 worker enough for the hotel? | P07 capacity: about 20 bookings a day, peak a few per minute; one email per second per worker | rejections only in an artificial burst | At the hotel's peak the queue holds 0–1 jobs; the burst of 30 in 0.1 s is a stress test, not a forecast | A model; revisit with real traffic (ADR-004) |
