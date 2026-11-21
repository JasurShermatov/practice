# Observed runs — P08

**Label:** Observed — every block below is real output copied from a run (full logs in
[logs/](logs/)). **Environment:** Linux container (kernel 6.18), 2 vCPU Intel Xeon 2.1 GHz, 8 GiB
RAM, Python 3.13.18, pytest 9.1.1, Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, SQLite 3.53.1,
redis-server 7.0.15, curl 8.5.0, Mermaid CLI 11.16.0. **Run date:** 2026-11-21 (portfolio build).
**Working directory:** `hotel-booking/` unless stated. Ports: the scripts use free ports; the
printed commands show the course's 5080. My Mac was not used; what only it can run is
listed in the README checklist.

## O1 · Start: the P07 safety net

Before any P08 change ([b0-baseline](logs/b0-baseline.txt)):

```text
$ python3 -m pytest -q
335 passed in 4.35s
$ python3 -m unittest
Ran 12 tests in 0.054s
OK
$ python3 -m tests.test_architecture
Contracts: 5 kept, 0 broken.
$ python3 -m pytest -q practices/*/checks
95 passed in 0.42s
```

## O2 · The old tests meet the new code

After the code change, before touching any test or the contract ([b1](logs/b1-old-tests-after-the-code-change.txt)):

```text
FAILED tests/test_api_sqlite.py::test_main_without_a_flag_starts_the_web_app
FAILED tests/test_api_sqlite.py::test_main_db_and_port_options_reach_the_server
FAILED tests/test_architecture.py::test_every_class_lives_in_one_of_the_four_modules_or_the_api_edge
FAILED tests/test_openapi_contract.py::test_every_route_is_in_the_contract_and_every_operation_is_served
4 failed, 331 passed in 4.18s
```

Each one is an expected consequence (new `ServerOptions`, three new edge files, `GET /stats` not yet
in the contract — the contract test caught the code being ahead of the contract). The 8 booking
tests, the 4 P07 API tests and the race pins passed unchanged.

## O3 · Steps 1 and 4: the measurement, repeated

`run_experiment.py` ([raw](logs/experiment-raw.txt)) — one "No cache" and one Redis run of five:

```text
--- course / cache off / round 2 (app CPU 0.79 s, redis CPU 0.0 s)
1000 searches for 2026-11-12 to 2026-11-14
Average: 0.9 ms
p95: 1.4 ms
Total: 0.9 s
GET /stats difference: {"searches":1000,"databaseQueries":2000,"cacheHits":0,"cacheMisses":0,"cacheErrors":0}
--- course / cache redis / round 2 (app CPU 0.58 s, redis CPU 0.04 s)
1000 searches for 2026-11-12 to 2026-11-14
Average: 0.7 ms
p95: 1.0 ms
Total: 0.7 s
GET /stats difference: {"searches":1000,"databaseQueries":2,"cacheHits":999,"cacheMisses":1,"cacheErrors":0}
```

Summary of all runs ([experiment-summary](logs/experiment-summary.md); median, min–max):

```text
| course   | off    | 5 | 2000  | 0 / 0     | 0.92 (0.79-1.04) | 1.31 (1.25-1.39)  | ... | 0.76 (0.71-0.88) app CPU s |
| course   | redis  | 5 | 2     | 999 / 1   | 0.72 (0.66-0.76) | 1.13 (0.97-1.17)  | ... | 0.60 (0.58-0.64) + 0.05 Redis |
| course   | memory | 5 | 2     | 999 / 1   | 0.57 (0.51-0.65) | 0.89 (0.61-0.95)  | ... | 0.51 (0.47-0.55) |
| rooms40  | off    | 3 | 40000 | 0 / 0     | 1.51 (1.41-1.53) | 1.86 (1.65-1.94)  | ... | 1.30 (1.20-1.33) |
| rooms40  | redis  | 3 | 40    | 999 / 1   | 0.89 (0.78-0.91) | 1.22 (1.13-1.25)  | ... | 0.74 (0.66-0.74) + 0.05 |
| clients8 | off    | 3 | 2000  | 0 / 0     | 6.39 (5.99-6.95) | 10.04 (8.99-11.03)| ... | 0.87 (0.87-0.97) |
| clients8 | redis  | 3 | 16    | 992 / 8   | 4.83 (4.79-5.35) | 7.19 (6.99-8.05)  | ... | 0.61 (0.61-0.68) + 0.02 |
```

The concurrent runs show the stampede in every run: 8 clients start together, 8 misses, 16 queries.

## O4 · Step 5 and Step 6: stale, then fresh

[cache-behaviour](logs/cache-behaviour.txt) § C (`python main.py --no-invalidation`), shortened bodies:

```text
GET  search 12-14 Nov   -> 200 R7, R8   X-Cache: miss
POST maya-r7.json       -> 201 {"id":"R101","status":"Confirmed","notificationFailed":false}
GET  search 12-14 Nov   -> 200 R7, R8   X-Cache: hit      <- STALE: R7 is booked
POST omar-r7.json       -> 409 {"title":"Unavailable","status":409,"detail":"The room is booked for at least one night of this stay."}
```

§ D (`python main.py`, invalidation on):

```text
GET  search 12-14 Nov   -> 200 R7, R8   X-Cache: miss
POST maya-r7.json       -> 201 R101
GET  search 12-14 Nov   -> 200 R8       X-Cache: miss     <- fresh: version 1
POST omar-r7.json       -> 409 Unavailable
$ redis-cli KEYS 'availability:*'
availability:version
availability:v0:2026-11-12:2026-11-14
availability:v1:2026-11-12:2026-11-14
```

## O5 · Step 6 item 3: the tests can fail

[break-the-cache](logs/break-the-cache.txt) — 9 mutations on copies, every one caught:

```text
Unchanged copy: unittest Ran 14 tests in 0.051s / OK; P08 pytest files: 116 passed in 3.15s

1. Step 6 item 3: the invalidate line (and its if) is removed from POST
   unittest: Ran 14 tests in 0.042s / FAILED (failures=1)
   FAILED unittest test_a_booking_and_a_cancel_make_the_next_search_fresh
...
Every mutation was caught; the project itself was not changed.
```

## O6 · Step 7: hot key, versions, expiry, busy sale

§ E and § F:

```text
$ python3 tools/measure.py 2026-12-31 2027-01-02
GET /stats difference: {"searches":1000,"databaseQueries":2,"cacheHits":999,"cacheMisses":1,"cacheErrors":0}
$ redis-cli KEYS 'availability:*'          (after one New Year booking and one search)
availability:v0:2026-12-31:2027-01-02
availability:version
availability:v1:2026-12-31:2027-01-02
(waiting 31 seconds: longer than the TTL)
$ redis-cli KEYS 'availability:*'
availability:version

1000 New Year searches and 20 bookings in 1.4 s     (40 rooms, a booking after every 50th search)
GET /stats difference: {"searches":1000,"databaseQueries":860,"cacheHits":980,"cacheMisses":20,"cacheErrors":0}
```

## O7 · Step 8: Redis stops while the app runs

§ G:

```text
GET  search (twice)    -> 200 R7, R8  X-Cache: miss, then hit
(redis-server stopped)
GET  search            -> 200 R7, R8  X-Cache: bypass
POST maya-r7.json      -> 201 R101
GET  search            -> 200 R8      X-Cache: bypass
POST maya-r7.json      -> 409 Unavailable
{"searches":4,"databaseQueries":10,"cacheHits":1,"cacheMisses":1,"cacheErrors":3}
(redis-server started again, empty)
GET  search            -> 200 R8      X-Cache: miss, then hit
```

## O8 · No regression, and the race is still there

```text
$ HOTEL_REDIS_PORT=16391 python3 -I practices/P07-capacity-api-design/evidence/api_check.py hotel-booking --port 5087
Result: 21 of 21 answers exactly as expected, 1 restart.
$ python3 main.py --race
Maya: Accepted R101
Omar: Accepted R102
Confirmed reservations for R7 on 12-14 Nov: 2
Double booking! Both requests checked before either one saved.
```

Race pins ×10: `7 passed, 6 deselected` ten times ([f-race-pins-10](logs/f-race-pins-10.txt)).

## O9 · Everything at the end

```text
$ python3 -m unittest -v
Ran 14 tests ... OK
$ python3 -m tests.test_architecture
Contracts: 6 kept, 0 broken.
$ python3 -m pytest -q
427 passed
$ python3 -m mypy
Success: no issues found in 31 source files
```

Document checks P05–P08 and the six diagram renders: [f-doc-checks](logs/f-doc-checks.txt), [mmdc](logs/mmdc.txt).
