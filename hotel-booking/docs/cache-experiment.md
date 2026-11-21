# Cache experiment: the free-room search

The database is the source of truth. Redis keeps copies of search answers for 30 seconds
(cache-aside, key `availability:v{version}:{checkIn}:{checkOut}`, value such as `R7,R8`); a
committed booking or cancel raises the version. Booking and cancelling never read the cache.
The decision and its costs: [ADR-002](adr-002-cache-availability.md).

Every number below is **Observed** (actually run) unless a line says otherwise. Raw output:
[experiment-raw.txt](../../practices/P08-cache-scale-experiment/evidence/logs/experiment-raw.txt),
[experiment-results.json](../../practices/P08-cache-scale-experiment/evidence/logs/experiment-results.json),
[cache-behaviour.txt](../../practices/P08-cache-scale-experiment/evidence/logs/cache-behaviour.txt).

## Measurements

**Workload (the course's).** 1,000 searches for 12–14 Nov, one after another, over one keep-alive
HTTP connection, with `tools/measure.py`; an empty reservations table; rooms R7 and R8. Before
every run: a fresh database file, the app started with `python main.py --cache <kind>`, 50
warm-up searches for another stay, and — for Redis — `FLUSHALL`, so the measured stay starts with
a miss. Five runs per configuration, interleaved (off, redis, memory, off, …) so that a slow
moment of the machine does not land on one configuration only. Table cells: **median of the five
runs** (min–max in the second table).

**Environment.** Linux container (kernel 6.18), 2 vCPU Intel Xeon 2.1 GHz, 8 GiB RAM;
Python 3.13.18, Starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0 (one process, access log on);
SQLite 3.53.1 (a file); redis-server 7.0.15 on localhost; the measurement tool on the same machine.
Run on 2026-11-21 by `evidence/run_experiment.py`. Times from this container; the Mac will differ.

| Run | Searches | Database queries | Cache hits | Average | p95 |
|---|---|---|---|---|---|
| No cache | 1,000 | 2,000 | 0 | 0.92 ms | 1.31 ms |
| Cache-aside, TTL 30 s (Redis) | 1,000 | 2 | 999 | 0.72 ms | 1.13 ms |
| Cache-aside, TTL 30 s, in the app's memory (`--cache memory`, extra) | 1,000 | 2 | 999 | 0.57 ms | 0.89 ms |

S1 asks for p95 ≤ 1 second: both course runs meet it here, more than 700 times over — with two
rooms, one client and SQLite on the same machine.
The cache removed 1,998 of 2,000 database queries (99.9 %); with 40 rooms it removed 39,960 of
40,000 — measured, not only multiplied (scale table below).

The spread of the five runs (min–max) and the rest of each run:

| Run | Average ms | p95 ms | p99 ms | Searches/s | App CPU s per 1,000 | Redis CPU s per 1,000 |
|---|---|---|---|---|---|---|
| No cache | 0.79–1.04 | 1.25–1.39 | 1.41–1.70 | 961–1261 (median 1081) | 0.71–0.88 (median 0.76) | 0.00 |
| Redis | 0.66–0.76 | 0.97–1.17 | 1.14–1.35 | 1319–1509 (median 1389) | 0.58–0.64 (median 0.60) | 0.04–0.05 |
| In memory | 0.51–0.65 | 0.61–0.95 | 0.70–1.10 | 1540–1960 (median 1755) | 0.47–0.55 (median 0.51) | 0.00 |

What I read from it:

- **The counts are the real result.** 2,000 → 2 queries in every run, exactly as predicted
  (one question per room per search, only the first search misses). They do not depend on the
  machine.
- **The times improve, but less than the counts.** With Redis the average fell by about 22 %
  (0.92 → 0.72 ms) and p95 by about 14 % (1.31 → 1.13 ms). The ranges do not overlap, so the
  difference is not noise — but it is small, because a SQLite query on a local file costs only
  microseconds, while a hit still costs two Redis round trips (GET the version, GET the copy)
  and a thread-pool hop. The in-process cache is faster still (no network hop) but would not
  work with two app instances (see the hot-key section).
- **CPU per 1,000 searches** (app + Redis, read from `/proc`; 10 ms resolution): 0.76 s → 0.65 s
  with Redis (−14 %), 0.51 s in memory (−33 %), and with 40 rooms 1.31 s → 0.79 s (−40 %).
  S6 asks for "at least 20 % less energy per 1,000 searches": CPU time is only a proxy for energy,
  and with two rooms Redis does **not** reach 20 % here; with the 40 rooms of the capacity
  estimate it does. The S6 target itself is still *to agree*.

### Scale: more rooms, more clients at once

The same procedure, three runs each (median, min–max in brackets):

| Scenario | Cache | Database queries | Hits / misses | Average ms | p95 ms | Searches/s |
|---|---|---|---|---|---|---|
| 40 rooms (P07 estimate), 1 client | off | 40,000 | 0 / 0 | 1.51 (1.41–1.53) | 1.86 (1.65–1.94) | 661 |
| 40 rooms, 1 client | Redis | 40 | 999 / 1 | 0.89 (0.78–0.91) | 1.22 (1.13–1.25) | 1122 |
| 2 rooms, 8 clients at the same time | off | 2,000 | 0 / 0 | 6.39 (5.99–6.95) | 10.04 (8.99–11.03) | 1228 |
| 2 rooms, 8 clients at the same time | Redis | 16 | 992 / 8 | 4.83 (4.79–5.35) | 7.19 (6.99–8.05) | 1647 |

- The cost of a search without a cache **grows with the number of rooms** (1.51 ms for 40 rooms
  against 0.92 ms for 2); with the cache it barely moves (0.89 ms against 0.72 ms), because a hit
  does not ask about rooms at all. Here the cache pays off clearly: −41 % average, +70 % searches
  a second.
- With **8 clients at once** every client waits for the others (one uvicorn process, 2 vCPU shared
  with the measurement tool), so the times are higher; the cache still gives −28 % p95 and +34 %
  throughput.
- **8 misses, not 1, in every concurrent run:** the 8 clients started together, all found no copy
  and all asked the database (16 queries) before the first copy was stored. That is the "two
  misses at the same moment both ask the database" cost of ADR-002 (a cache stampede), seen for
  real. Harmless with 2 rooms; with 40 rooms and hundreds of guests after an invalidation it is
  the next thing to fix (one loader per key, or refresh before expiry).

### Limitations (why these are not the hotel's production numbers)

- **SQLite, not PostgreSQL.** The app ran on a local SQLite file; the PostgreSQL driver cannot be
  installed here. Against PostgreSQL in Docker every query is a network round trip, so the
  "No cache" row would be slower and the cache's gain larger. To repeat on the Mac (**Proposed**):
  `docker compose up -d`, `python main.py --db postgres`, the same tool.
- **Redis 7.0 on localhost**, not `redis:8` in Docker Desktop; the commands used (GET, SET EX, INCR)
  behave the same, the network hop on a Mac is longer.
- **One machine for everything:** the tool, the app and Redis share 2 vCPU; a client on another
  machine would see network time too. One uvicorn process; no load balancer.
- **Sequential load is not the 200-a-minute peak.** 1,000 searches one after another measure the
  cost of one search, not behaviour under the estimated peak with many guests — that is P23.
- **Short runs** (under 2 s each) and five repetitions: enough to see that the ranges do not
  overlap, not enough for fine differences. Single searches up to 36 ms appear (max column in the
  raw log) — scheduler or garbage-collector pauses; p95/p99 hide them by design.
- CPU time is a proxy for energy, measured with 10 ms resolution, app and Redis only.

## Stale result (Step 5, before invalidation)

Run for real with `python main.py --no-invalidation` (a switch for this experiment only), an empty
database and an empty cache; four `curl` calls within 30 seconds
([cache-behaviour.txt § C](../../practices/P08-cache-scale-experiment/evidence/logs/cache-behaviour.txt)):

1. Search 12–14 Nov: **200 R7 and R8**, `X-Cache: miss` — the copy `R7,R8` is kept for 30 s.
2. Maya books R7 for 12–14 Nov: **201 R101** — saved in the database; the copy is not touched.
3. Search again: **200 R7 and R8**, `X-Cache: hit` — **STALE**: R7 is booked, the copy says free.
4. Omar asks for R7 for 13–15 Nov: **409 Unavailable** — booking asks the database, not the cache,
   so the booking rule holds and nobody is double-booked.

The same is pinned as a test: `test_stale_result_without_invalidation_known_trade_off`
(tests/test_api_cache.py) and `test_step5_the_stale_result_through_the_real_wiring`
(tests/test_cache_wiring.py, SQLite + real Redis). Without invalidation only the TTL ends the stale
copy: the test moves the clock 30 s on and the search shows R8 only.

## After invalidation (Step 6)

The same four requests with invalidation on (§ D of the log): the third search answers
**R8 only** (`X-Cache: miss`), because Maya's booking raised `availability:version` from 0 to 1
and the search built the new key `availability:v1:2026-11-12:2026-11-14`. Omar still gets 409.
Cancelling R101 raised the version to 2 and the next search showed R7 and R8 again. A 409, a 400
and a 404 change nothing and do not raise the version (tested). Removing the invalidate line from
POST makes the course's test `test_a_booking_and_a_cancel_make_the_next_search_fresh` fail at its
second search (and eight more) — [break-the-cache.txt](../../practices/P08-cache-scale-experiment/evidence/logs/break-the-cache.txt).

## Hot key and the next bottleneck (Step 7)

- **One key gets everything.** 1,000 searches for 31 Dec–2 Jan: 999 hits, 1 miss, 2 queries;
  `KEYS availability:*` shows the single key `availability:v0:2026-12-31:2027-01-02` (§ E). If Redis
  ran on several servers, that key would still live on one of them: that server does the work of
  the whole sale. Fixes for later: a very short copy inside each app instance in front of Redis,
  or several copies of the key.
- **Every booking throws the copy away.** After one New Year booking the next search built
  `…:v1:…` and missed; for a while both versions sat side by side, and 31 s later only
  `availability:version` was left — the old copy expired by itself (TTL 29 s seen just after the
  booking).
- **A busy sale, measured** (§ F, 40 rooms): 1,000 New Year searches with a booking after every
  50th → 20 bookings, **980 hits / 20 misses (98 %)**, 860 database queries (20 misses × 40 rooms +
  20 bookings × 3). Without the cache the same searches would cost 40,000 queries. The hit rate
  falls with the booking rate: one miss per booking.
- **The bottleneck moved.** Before the cache the searches were the database's main work (2,000
  of 2,000 queries in the course run). Now searches cost Redis, and what is left for the database
  is mostly `POST /reservations`: 3 questions per booking, which must be exact and cannot be
  cached. Two bookings of R7 at the same moment can still both pass the check — the race from P03,
  still pinned by tests. That is the next bottleneck and the next defect: L05 and P09.

## When Redis stops (Step 8)

Observed (§ G): with the app running I stopped redis-server. The search still answered **200**
from the database (`X-Cache: bypass`), Maya's booking was saved and answered **201**, her retry
got 409, and `cacheErrors` counted the 3 failed cache commands; the app log names each one. After
Redis started again (empty: no persistence on purpose) the next search missed and the one after
hit. This is my own choice, different from the course's reference (where a search fails while
Redis is down and a booking is saved but answered with an error) — the reasons are in ADR-002.

## How to repeat

```text
python main.py --cache off        # terminal 1: the "No cache" row      (Ctrl+C, then:)
python main.py                    # terminal 1: Redis (docker compose up -d first)
docker compose exec cache redis-cli FLUSHALL
python tools/measure.py           # terminal 2, after each start
python tools/measure.py --clients 8
python tools/measure.py 2026-12-31 2027-01-02
```

Everything above at once, in a container: `python3 -I practices/P08-cache-scale-experiment/evidence/run_experiment.py hotel-booking`
and `…/cache_behaviour.py hotel-booking` (they start their own redis-server).
The script's CPU sampling reads `/proc` and is Linux-only; on macOS it skips that sampling (the CPU
columns show "n/a") and measures everything else the same way.
